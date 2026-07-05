"""
Service definitions and implementation for the ForgeAI Developer Plugin.
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

from .models import ImplementationReport
from .exceptions import DeveloperError
from .validators.architecture_validator import ArchitectureValidator
from .writers.workspace_writer import WorkspaceWriter
from .utils.pipeline import ImplementationContext, ImplementationPipeline
from .components import (
    DependencyGenerator,
    EnvironmentGenerator,
    ConfigurationGenerator,
    DatabaseGenerator,
    APIGenerator,
    BackendGenerator,
    FrontendGenerator,
    ImplementationReportGenerator,
)

logger = logging.getLogger("ForgeAI.Plugins.Developer")


class DeveloperService(ABC):
    """
    Interface for the Developer service.
    """

    @abstractmethod
    def implement_project(
        self, plan: ProjectPlan, spec: ArchitectureSpecification
    ) -> ImplementationReport:
        """
        Generates code and configuration files based on planning and architecture inputs.

        Args:
            plan (ProjectPlan): The decomposed project plan.
            spec (ArchitectureSpecification): The designed software architecture specification.

        Returns:
            ImplementationReport: The report summarizing generated files and status.
        """
        pass


class ForgeAIDeveloper(DeveloperService):
    """
    Concrete Developer Service implementation.
    Validates specifications, runs the generator pipeline in-memory, and writes output atomically.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """
        Initializes the developer service with the service registry.

        Args:
            registry (ServiceRegistry): System service container.
        """
        self._registry = registry
        self.validator = ArchitectureValidator()
        self.writer = WorkspaceWriter(self._event_bus)

        # Assemble the sequential developer compiler pipeline
        self.steps = [
            DependencyGenerator(),
            EnvironmentGenerator(),
            ConfigurationGenerator(),
            DatabaseGenerator(),
            APIGenerator(),
            BackendGenerator(),
            FrontendGenerator(),
            ImplementationReportGenerator(),
        ]
        self.pipeline = ImplementationPipeline(self.steps, self._event_bus)

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
    def _config_service(self) -> ConfigurationService:
        return self._registry.resolve(ConfigurationService)  # type: ignore[type-abstract]

    def implement_project(
        self, plan: ProjectPlan, spec: ArchitectureSpecification
    ) -> ImplementationReport:
        # 1. Resolve workspace path from config
        try:
            system_settings = self._config_service.get_system_settings()
            workspace_path = system_settings.workspace_dir
        except Exception as e:
            logger.error(f"Failed to resolve workspace settings: {e}")
            raise DeveloperError(f"Configuration resolution failed: {e}") from e

        # 2. Early Architecture and Spec Validation
        self.validator.validate(plan, spec, workspace_path)

        logger.info(
            f"Initiating project implementation for Project ID: '{spec.project_id}'"
        )

        # 3. Construct Shared Context
        config = self._config_service.get_full_config()
        context = ImplementationContext(
            project_plan=plan,
            architecture=spec,
            workspace=workspace_path,
            model_router=self._model_router,
            configuration=config,
            memory=self._memory,
            logger=logger,
        )

        # 4. Run Compiler Pipeline in-memory
        try:
            self.pipeline.execute(context)
        except Exception as e:
            logger.error(f"Implementation pipeline execution failed: {e}")
            # Raise DeveloperError so caller knows generation failed
            if not isinstance(e, DeveloperError):
                raise DeveloperError(f"Pipeline execution failed: {e}") from e
            raise

        # 5. Atomic Workspace Write
        try:
            self.writer.write_files(
                workspace_path, context.generated_files, spec.project_id
            )
        except Exception as e:
            logger.error(f"Failed to write files to workspace: {e}")
            self._event_bus.publish(
                Event(
                    event_type="developer.failed",
                    data={
                        "project_id": spec.project_id,
                        "failed_step": "WorkspaceWriter",
                        "error": str(e),
                    },
                )
            )
            if not isinstance(e, DeveloperError):
                raise DeveloperError(f"Workspace write failed: {e}") from e
            raise

        # 6. Extract markdown report summary from the generated files
        report_summary = ""
        for gf in context.generated_files:
            if gf.file_type == "report":
                report_summary = gf.content
                break

        # 7. Construct ImplementationReport
        report = ImplementationReport(
            project_id=spec.project_id,
            files=context.generated_files,
            summary=report_summary,
            status="SUCCESS",
        )

        # 8. Save to memory
        try:
            report_dict = report.to_dict()
            self._memory.runtime.set_project_state("implementation_report", report_dict)
            self._memory.project.set_metadata("implementation_report", report_dict)
        except Exception as e:
            logger.error(f"Failed to store implementation report in memory: {e}")

        # 9. Publish Completed Event
        self._event_bus.publish(
            Event(
                event_type="developer.completed",
                data=report.to_dict(),
            )
        )

        logger.info("Project implementation completed successfully.")
        return report
