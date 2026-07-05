"""
Pipeline execution orchestrator for sequencing and running documentation sub-generators.
"""

import logging
from abc import ABC, abstractmethod
from typing import List

from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.model_router.service import ModelRouterService
from forge_core.configuration.models import ForgeConfig
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.models import TestReport

from ..models import GeneratedDocFile

logger = logging.getLogger("ForgeAI.Plugins.Documentation.Utils")


class DocContext:
    """
    Context container containing all input specifications and generated document state.
    """

    def __init__(
        self,
        project_plan: ProjectPlan,
        architecture: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        test_report: TestReport,
        workspace: str,
        model_router: ModelRouterService,
        event_bus: EventBusService,
        configuration: ForgeConfig,
        logger: logging.Logger,
    ) -> None:
        """Initializes the shared documentation pipeline context."""
        self.project_plan = project_plan
        self.architecture = architecture
        self.implementation_report = implementation_report
        self.test_report = test_report
        self.workspace = workspace
        self.model_router = model_router
        self.event_bus = event_bus
        self.configuration = configuration
        self.logger = logger
        self.generated_docs: List[GeneratedDocFile] = []
        self.progress_percentage: float = 0.0


class DocPipelineStep(ABC):
    """
    Abstract step in the documentation generation pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique human-readable identifier for this pipeline step."""
        pass

    @abstractmethod
    def run(self, context: DocContext) -> None:
        """
        Executes document compilation logic.

        Args:
            context (DocContext): The shared pipeline context.
        """
        pass


class DocPipeline:
    """
    Executes a sequence of DocPipelineSteps, broadcasting system progress events.
    """

    def __init__(
        self, steps: List[DocPipelineStep], event_bus: EventBusService
    ) -> None:
        """
        Initializes the pipeline with steps and system event bus.

        Args:
            steps (List[DocPipelineStep]): Steps to execute.
            event_bus (EventBusService): The system event bus.
        """
        self.steps = steps
        self.event_bus = event_bus

    def run(self, context: DocContext) -> None:
        """
        Executes each pipeline step, updating progress and emitting lifecycle events.

        Args:
            context (DocContext): The shared pipeline context.
        """
        total_steps = len(self.steps)
        if total_steps == 0:
            return

        for index, step in enumerate(self.steps):
            context.logger.info(f"Running step: {step.name}")

            # Emit step started event
            start_event = Event(
                event_type="documentation.step_started",
                data={
                    "step_name": step.name,
                    "project_id": context.architecture.project_id,
                },
            )
            self.event_bus.publish(start_event)

            # Run step logic
            step.run(context)

            # Update progress
            context.progress_percentage = ((index + 1) / total_steps) * 100.0
            context.logger.info(
                f"Step '{step.name}' completed. Progress: {context.progress_percentage:.1f}%"
            )

            # Emit step completed event
            completed_event = Event(
                event_type="documentation.step_completed",
                data={
                    "step_name": step.name,
                    "project_id": context.architecture.project_id,
                    "progress": context.progress_percentage,
                },
            )
            self.event_bus.publish(completed_event)
