"""
Service definitions and concrete implementation for the ForgeAI Reviewer Plugin.
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import Any

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.kernel.lifecycle import LifecycleComponent
from forge_core.model_router.service import ModelRouterService
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from forge_core.configuration.service import ConfigurationService

from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport

from .models import ReviewReport, ReviewManifest
from .exceptions import ReviewerError, ReviewerValidationError, ReviewerAnalysisError
from .validators.reviewer_validator import ReviewerValidator
from .utils.reviewer_pipeline import ReviewerContext, ReviewerPipeline
from .components.report_generator import ReviewReportGenerator
from .writers.reviewer_writer import ReviewerWorkspaceWriter

logger = logging.getLogger("ForgeAI.Plugins.Reviewer")


class ReviewerService(ABC):
    """Interface for the Code Review service."""

    @abstractmethod
    def review_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: Any,
        doc_report: Any,
    ) -> ReviewReport:
        """
        Runs the complete code review pipeline across the generated project.

        Args:
            plan (ProjectPlan): The project requirements plan.
            spec (ArchitectureSpecification): The software architecture spec.
            report (ImplementationReport): The implementation report containing source files.
            test_report (Any): Optional test execution report.
            doc_report (Any): Optional documentation generation report.

        Returns:
            ReviewReport: The generated code review report.
        """
        pass


class ForgeAIReviewer(ReviewerService, LifecycleComponent):
    """Concrete implementation of the Code Review service."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self.validator = ReviewerValidator()

    @property
    def _model_router(self) -> ModelRouterService:
        return self._registry.resolve(ModelRouterService)  # type: ignore[type-abstract]

    @property
    def _event_bus(self) -> EventBusService:
        return self._registry.resolve(EventBusService)  # type: ignore[type-abstract]

    @property
    def _memory(self) -> MemoryService:
        return self._registry.resolve(MemoryService)  # type: ignore[type-abstract]

    @property
    def _config(self) -> ConfigurationService:
        return self._registry.resolve(ConfigurationService)  # type: ignore[type-abstract]

    def initialize(self) -> None:
        """Lifecycle initialization hook."""
        self.writer = ReviewerWorkspaceWriter(self._event_bus)
        self.pipeline = ReviewerPipeline(self._event_bus)
        logger.info("Reviewer service initialized.")

    def shutdown(self) -> None:
        """Lifecycle shutdown hook."""
        logger.info("Reviewer service shut down.")

    def review_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: Any,
        doc_report: Any,
    ) -> ReviewReport:
        try:
            system_settings = self._config.get_system_settings()
            workspace_path = system_settings.workspace_dir
        except Exception as e:
            logger.error(f"Failed to resolve workspace settings: {e}")
            raise ReviewerError(f"Configuration resolution failed: {e}") from e

        try:
            self.validator.validate(plan, spec, report, workspace_path)
        except ReviewerValidationError as ve:
            logger.error(f"Reviewer validation checks failed: {ve}")
            self._event_bus.publish(
                Event(
                    event_type="reviewer.failed",
                    data={
                        "project_id": spec.project_id if spec else "",
                        "error": str(ve),
                    },
                )
            )
            raise

        logger.info(f"Initiating code review for Project ID: '{spec.project_id}'")

        full_config = self._config.get_full_config()
        reviewer_config = full_config.reviewer
        rule_policy = reviewer_config.get("rules") or {}

        context = ReviewerContext(workspace_path, rule_policy)
        try:
            self.pipeline.execute(context)
        except Exception as e:
            logger.error(f"Review scan pipeline failed: {e}", exc_info=True)
            self._event_bus.publish(
                Event(
                    event_type="reviewer.failed",
                    data={"project_id": spec.project_id, "error": str(e)},
                )
            )
            raise ReviewerAnalysisError(f"Pipeline execution failed: {e}") from e

        llm_review_enabled = reviewer_config.get("llm_review", True)
        final_report = ReviewReportGenerator.generate_report(
            project_id=spec.project_id,
            findings=context.findings,
            llm_review_enabled=llm_review_enabled,
            model_router=self._model_router,
        )

        from forge_plugins.reviewer.rules import registry as rules_registry

        rules_run_ids = [
            r.rule_id for r in rules_registry.get_enabled_rules(rule_policy)
        ]
        manifest = ReviewManifest(
            files_scanned=context.files_scanned,
            scan_duration_ms=context.scan_duration_ms,
            rules_run=rules_run_ids,
            ignored_files=context.ignored_files,
            tool_version="1.0.0",
            timestamp=time.time(),
        )

        try:
            self.writer.write_reports(workspace_path, final_report, manifest)
        except Exception as e:
            logger.error(f"Failed to write review reports to disk: {e}")
            raise ReviewerAnalysisError(f"Failed to write deliverables: {e}") from e

        try:
            report_dict = final_report.to_dict()
            self._memory.runtime.set_project_state("review_report", report_dict)
            self._memory.project.set_metadata("review_report", report_dict)
        except Exception as e:
            logger.error(f"Failed storing review report in memory: {e}")

        if reviewer_config.get("block_release", False):
            min_quality_score = reviewer_config.get("min_quality_score", 50.0)
            if final_report.quality_score < min_quality_score:
                err_msg = (
                    f"Reviewer quality gate failed: quality score {final_report.quality_score} "
                    f"is below the minimum allowed ({min_quality_score})."
                )
                logger.error(err_msg)
                raise ReviewerError(err_msg)

        self._event_bus.publish(
            Event(
                event_type="reviewer.completed",
                data={
                    "project_id": spec.project_id,
                    "findings": len(context.findings),
                    "quality_score": final_report.quality_score,
                },
            )
        )

        logger.info(
            f"Code review completed successfully for project '{spec.project_id}'."
        )
        return final_report
