"""
Pipeline infrastructure for the Tester Plugin execution context and step sequencing.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from forge_core.event_bus.models import Event
from forge_core.event_bus.service import EventBusService
from forge_core.model_router.service import ModelRouterService
from forge_core.memory.service import MemoryService
from forge_core.configuration.models import ForgeConfig
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.models import GeneratedTestFile


class TestContext:
    """
    State container passed between test pipeline compilation steps.
    """

    def __init__(
        self,
        project_plan: ProjectPlan,
        architecture: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        workspace: str,
        model_router: ModelRouterService,
        event_bus: EventBusService,
        configuration: ForgeConfig,
        memory: MemoryService,
        logger: logging.Logger,
    ) -> None:
        """Initializes the shared testing context."""
        self.project_plan = project_plan
        self.architecture = architecture
        self.implementation_report = implementation_report
        self.workspace = workspace
        self.model_router = model_router
        self.event_bus = event_bus
        self.configuration = configuration
        self.memory = memory
        self.logger = logger
        self.generated_test_files: List[GeneratedTestFile] = []
        self.progress_percentage: float = 0.0


class TestPipelineStep(ABC):
    """
    Abstract interface for individual test code/spec generation steps.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier name for this compilation step."""
        pass

    @abstractmethod
    def run(self, context: TestContext) -> None:
        """
        Executes test code generation logic for this step.

        Args:
            context (TestContext): The shared pipeline context.
        """
        pass


class TestPipeline:
    """
    Executes a sequence of TestPipelineSteps, emitting progress events.
    """

    def __init__(
        self, steps: List[TestPipelineStep], event_bus: EventBusService
    ) -> None:
        """
        Initializes the pipeline with steps and system event bus.

        Args:
            steps (List[TestPipelineStep]): Steps to execute.
            event_bus (EventBusService): Core system event bus.
        """
        self.steps = steps
        self.event_bus = event_bus

    def execute(self, context: TestContext) -> None:
        """
        Executes all registered steps sequentially.

        Args:
            context (TestContext): Shared testing context.
        """
        project_id = context.architecture.project_id
        context.logger.info(
            f"Starting test generation pipeline for project: {project_id}"
        )

        self.event_bus.publish(
            Event(
                event_type="tester.started",
                data={
                    "project_id": project_id,
                    "total_steps": len(self.steps),
                },
            )
        )

        for i, step in enumerate(self.steps):
            context.logger.info(f"Running test pipeline step: {step.name}")
            try:
                step.run(context)
            except Exception as e:
                context.logger.error(f"Step '{step.name}' failed: {e}")
                self.event_bus.publish(
                    Event(
                        event_type="tester.failed",
                        data={
                            "project_id": project_id,
                            "failed_step": step.name,
                            "error": str(e),
                        },
                    )
                )
                raise

            # Update progress
            progress = ((i + 1) / len(self.steps)) * 100
            context.progress_percentage = progress

            self.event_bus.publish(
                Event(
                    event_type="tester.progress_updated",
                    data={
                        "project_id": project_id,
                        "step": step.name,
                        "progress": progress,
                        "files_generated": len(context.generated_test_files),
                    },
                )
            )

        context.logger.info("Test pipeline execution completed successfully.")
