"""
Service definitions and implementation for the ForgeAI Documentation Plugin.
"""

import logging
from abc import ABC, abstractmethod

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from forge_core.configuration.service import ConfigurationService

from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.models import TestReport

from .models import DocumentationReport
from .exceptions import (
    DocumentationError,
    DocValidationError,
    DocInferenceError,
    DocWriteError,
)
from .validators.doc_validator import DocValidator
from .writers.doc_workspace_writer import DocWorkspaceWriter
from .utils.doc_pipeline import DocContext, DocPipeline
from .components import (
    ProjectDocGenerator,
    DeveloperDocGenerator,
    ApiDocGenerator,
    ArchitectureDocGenerator,
    UserDocGenerator,
    ReleaseDocGenerator,
    DocSummaryGenerator,
)

logger = logging.getLogger("ForgeAI.Plugins.Documentation")


class DocumentationService(ABC):
    """
    Interface for the Documentation service.
    """

    @abstractmethod
    def document_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: TestReport,
    ) -> DocumentationReport:
        """
        Generates comprehensive documentation for the project, covering READMEs, APIs, Mermaid graphs, guides, etc.

        Args:
            plan (ProjectPlan): The project requirements plan.
            spec (ArchitectureSpecification): The software architecture spec.
            report (ImplementationReport): The implementation report containing source files.
            test_report (TestReport): The test report containing test files and stats.

        Returns:
            DocumentationReport: The generated documentation report.
        """
        pass


class ForgeAIDocumentation(DocumentationService):
    """
    Concrete implementation of the Documentation service running sub-generator pipelines.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """Initializes the documentation service resolving dependencies."""
        self._model_router = registry.resolve(ModelRouterService)  # type: ignore[type-abstract]
        self._event_bus = registry.resolve(EventBusService)  # type: ignore[type-abstract]
        self._memory = registry.resolve(MemoryService)  # type: ignore[type-abstract]
        self._config = registry.resolve(ConfigurationService)  # type: ignore[type-abstract]
        self.validator = DocValidator()
        self.writer = DocWorkspaceWriter(self._event_bus)

    def document_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: TestReport,
    ) -> DocumentationReport:
        """
        Runs validation checks, invokes the compilation pipeline of generators,
        writes output docs to the workspace, compiles the manifest, records to memory,
        and publishes lifecycle events.
        """
        logger.info(
            f"Initiating autonomous technical writer for Project ID: '{spec.project_id if spec else 'unknown'}'"
        )

        # 1. Resolve workspace path
        workspace_path = ""
        try:
            settings = self._config.get_system_settings()
            workspace_path = settings.workspace_dir
        except Exception as e:
            raise DocumentationError(
                f"Failed to resolve system workspace settings: {e}"
            ) from e

        # 2. Run validations
        try:
            self.validator.validate(plan, spec, report, test_report, workspace_path)
        except DocValidationError as val_err:
            logger.error(f"Doc validation checks failed: {val_err}")
            self._event_bus.publish(
                Event(
                    event_type="documentation.validation_failed",
                    data={
                        "project_id": spec.project_id if spec else "",
                        "error": str(val_err),
                    },
                )
            )
            raise

        # 3. Setup context
        context = DocContext(
            project_plan=plan,
            architecture=spec,
            implementation_report=report,
            test_report=test_report,
            workspace=workspace_path,
            model_router=self._model_router,
            event_bus=self._event_bus,
            configuration=self._config.get_full_config(),
            logger=logger,
        )

        # 4. Initialize pipeline steps
        steps = [
            ProjectDocGenerator(),
            DeveloperDocGenerator(),
            ApiDocGenerator(),
            ArchitectureDocGenerator(),
            UserDocGenerator(),
            ReleaseDocGenerator(),
            DocSummaryGenerator(),
        ]
        pipeline = DocPipeline(steps, self._event_bus)

        # 5. Execute pipeline
        try:
            pipeline.run(context)
        except Exception as err:
            logger.error(f"Documentation generation step failed: {err}")
            self._event_bus.publish(
                Event(
                    event_type="documentation.generation_failed",
                    data={"project_id": spec.project_id, "error": str(err)},
                )
            )
            raise DocInferenceError(
                f"Failed to generate documentation pipeline output: {err}"
            ) from err

        # 6. Write documentation to workspace
        try:
            self.writer.write_docs(
                workspace=workspace_path,
                doc_files=context.generated_docs,
                project_id=spec.project_id,
                model_router=self._model_router,
            )
        except Exception as write_err:
            logger.error(f"Workspace doc commit failed: {write_err}")
            raise DocWriteError(
                f"Failed to commit documentation to workspace: {write_err}"
            ) from write_err

        # 7. Extract index dashboard contents
        report_summary = ""
        for doc in context.generated_docs:
            if doc.category == "summary":
                report_summary = doc.content
                break

        # 8. Create documentation report object
        doc_report = DocumentationReport(
            project_id=spec.project_id,
            doc_files=context.generated_docs,
            status="SUCCESS",
            summary=report_summary,
        )

        # 9. Persist report details to memory service
        try:
            report_dict = doc_report.to_dict()
            self._memory.runtime.set_project_state("documentation_report", report_dict)
            self._memory.project.set_metadata("documentation_report", report_dict)
        except Exception as mem_err:
            logger.error(
                f"Failed to persist documentation report to memory registries: {mem_err}"
            )

        # 10. Publish finished event to bus
        self._event_bus.publish(
            Event(
                event_type="documentation.completed",
                data={
                    "project_id": spec.project_id,
                    "documents_compiled": len(context.generated_docs),
                },
            )
        )

        logger.info("Autonomous documentation compilation completed successfully.")
        return doc_report
