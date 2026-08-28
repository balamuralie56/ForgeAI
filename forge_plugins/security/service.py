"""
Service definitions and concrete implementation for the ForgeAI Security Plugin.
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
from forge_core.task_engine.service import TaskEngineService

from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport

from .models import SecurityReport, SecurityManifest, Severity
from .exceptions import SecurityError, SecurityValidationError, SecurityAnalysisError
from .validators.security_validator import SecurityValidator
from .utils.security_pipeline import SecurityContext, SecurityPipeline
from .components.report_generator import SecurityReportGenerator
from .writers.security_writer import SecurityWorkspaceWriter

logger = logging.getLogger("ForgeAI.Plugins.Security")


class SecurityService(ABC):
    """
    Interface for the Security Auditing service.
    """

    @abstractmethod
    def audit_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: Any,
        doc_report: Any,
    ) -> SecurityReport:
        """
        Runs the complete security scanning pipeline across the generated project.

        Args:
            plan (ProjectPlan): The project requirements plan.
            spec (ArchitectureSpecification): The software architecture spec.
            report (ImplementationReport): The implementation report containing source files.
            test_report (Any): Optional test execution report.
            doc_report (Any): Optional documentation generation report.

        Returns:
            SecurityReport: The generated security analysis report.
        """
        pass


class ForgeAISecurity(SecurityService, LifecycleComponent):
    """
    Concrete implementation of the Security Auditing service.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self.validator = SecurityValidator()
        self._orchestrator = None  # To be set on initialize

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

    @property
    def _task_engine(self) -> TaskEngineService:
        return self._registry.resolve(TaskEngineService)  # type: ignore[type-abstract]

    def initialize(self) -> None:
        """Lifecycle initialization hook."""
        self.writer = SecurityWorkspaceWriter(self._event_bus)
        self.pipeline = SecurityPipeline(self._task_engine, self._event_bus)
        logger.info("Security service service initialized.")

    def shutdown(self) -> None:
        """Lifecycle shutdown hook."""
        logger.info("Security service service shut down.")

    def audit_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: Any,
        doc_report: Any,
    ) -> SecurityReport:
        # 1. Resolve workspace path from config
        try:
            system_settings = self._config.get_system_settings()
            workspace_path = system_settings.workspace_dir
        except Exception as e:
            logger.error(f"Failed to resolve workspace settings: {e}")
            raise SecurityError(f"Configuration resolution failed: {e}") from e

        # 2. Run validations
        try:
            self.validator.validate(plan, spec, report, workspace_path)
        except SecurityValidationError as ve:
            logger.error(f"Security validation checks failed: {ve}")
            self._event_bus.publish(
                Event(
                    event_type="security.failed",
                    data={
                        "project_id": spec.project_id if spec else "",
                        "error": str(ve),
                    },
                )
            )
            raise

        logger.info(f"Initiating security audit for Project ID: '{spec.project_id}'")

        # 3. Retrieve rule policy settings
        full_config = self._config.get_full_config()
        security_config = full_config.security
        rule_policy = security_config.get("rules") or {}

        # 4. Execute Pipeline
        context = SecurityContext(workspace_path, rule_policy)
        try:
            self.pipeline.execute(context)
        except Exception as e:
            logger.error(f"Security scan pipeline failed: {e}", exc_info=True)
            self._event_bus.publish(
                Event(
                    event_type="security.failed",
                    data={"project_id": spec.project_id, "error": str(e)},
                )
            )
            raise SecurityAnalysisError(f"Pipeline execution failed: {e}") from e

        # 5. Trend Analysis (Security History)
        trend_summary = ""
        try:
            # Recompute scores to compare
            risk_score, security_score = SecurityReportGenerator.calculate_scores(
                context.findings
            )
            prev_score_dict = self._memory.project.get_metadata(
                f"security:score:{spec.project_id}"
            )
            if (
                prev_score_dict
                and isinstance(prev_score_dict, dict)
                and "score" in prev_score_dict
            ):
                prev_score = float(prev_score_dict["score"])
                delta = security_score - prev_score
                trend_summary = f"Security score changed by {delta:+.2f} points (Previous: {prev_score:.2f}, Current: {security_score:.2f})"
            else:
                trend_summary = f"First scan completed. Initial security score: {security_score:.2f} points."

            # Save score trend for next runs
            self._memory.project.set_metadata(
                f"security:score:{spec.project_id}",
                {"score": security_score, "timestamp": time.time()},
            )
            self._memory.runtime.set_project_state(
                f"security:score:{spec.project_id}",
                {"score": security_score, "timestamp": time.time()},
            )
        except Exception as e:
            logger.warning(f"Failed to track security score history: {e}")

        # 6. Generate Report
        llm_review_enabled = security_config.get("llm_review", True)
        final_report = SecurityReportGenerator.generate_report(
            project_id=spec.project_id,
            findings=context.findings,
            llm_review_enabled=llm_review_enabled,
            model_router=self._model_router,
            trend_summary=trend_summary,
        )

        # 7. Generate Manifest
        from forge_plugins.security.rules import registry as rules_registry

        rules_run_ids = [
            r.rule_id for r in rules_registry.get_enabled_rules(rule_policy)
        ]
        manifest = SecurityManifest(
            files_scanned=context.files_scanned,
            scan_duration_ms=context.scan_duration_ms,
            rules_run=rules_run_ids,
            ignored_files=context.ignored_files,
            tool_version="1.0.0",
            timestamp=time.time(),
        )

        # 8. Write audit artifacts to workspace
        try:
            self.writer.write_reports(workspace_path, final_report, manifest)
        except Exception as e:
            logger.error(f"Failed to write security reports to disk: {e}")
            raise SecurityAnalysisError(f"Failed to write deliverables: {e}") from e

        # 9. Store in memory
        try:
            report_dict = final_report.to_dict()
            self._memory.runtime.set_project_state("security_report", report_dict)
            self._memory.project.set_metadata("security_report", report_dict)
        except Exception as e:
            logger.error(f"Failed storing security report in memory: {e}")

        # 10. Check quality gates block_release rules
        if security_config.get("block_release", True):
            max_critical = security_config.get("max_critical", 0)
            max_high = security_config.get("max_high", 2)
            max_risk_score = security_config.get("max_risk_score", 30.0)

            crit_count = sum(
                1 for f in context.findings if f.severity == Severity.CRITICAL
            )
            high_count = sum(1 for f in context.findings if f.severity == Severity.HIGH)

            if crit_count > max_critical:
                err_msg = f"Security quality gate failed: {crit_count} Critical violations found (Max allowed: {max_critical})."
                logger.error(err_msg)
                raise SecurityError(err_msg)

            if high_count > max_high:
                err_msg = f"Security quality gate failed: {high_count} High violations found (Max allowed: {max_high})."
                logger.error(err_msg)
                raise SecurityError(err_msg)

            if final_report.risk_score > max_risk_score:
                err_msg = f"Security quality gate failed: Risk score {final_report.risk_score} exceeds maximum allowed ({max_risk_score})."
                logger.error(err_msg)
                raise SecurityError(err_msg)

        # 11. Publish finished event
        self._event_bus.publish(
            Event(
                event_type="security.completed",
                data={
                    "project_id": spec.project_id,
                    "findings": len(context.findings),
                    "security_score": final_report.security_score,
                },
            )
        )

        logger.info(
            f"Security audit completed successfully for project '{spec.project_id}'."
        )
        return final_report
