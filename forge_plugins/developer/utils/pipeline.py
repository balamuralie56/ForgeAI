"""
Pipeline execution engine for the Developer Plugin.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from forge_core.configuration.models import ForgeConfig
from forge_core.event_bus.models import Event
from forge_core.event_bus.service import EventBusService
from forge_core.memory.service import MemoryService
from forge_core.model_router.service import ModelRouterService
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import GeneratedFile


@dataclass
class ImplementationContext:
    """Carries state across all generators in the Developer Plugin pipeline."""

    project_plan: ProjectPlan
    architecture: ArchitectureSpecification
    workspace: str
    model_router: ModelRouterService
    configuration: ForgeConfig
    memory: MemoryService
    logger: logging.Logger
    generated_files: List[GeneratedFile] = field(default_factory=list)
    progress_percentage: float = 0.0


class PipelineStep(ABC):
    """Abstract interface representing a single generator step in the pipeline."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the human-readable name of the step."""
        pass

    @abstractmethod
    def run(self, context: ImplementationContext) -> None:
        """
        Executes the generator step, modifying the context in-place.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        pass


class ImplementationPipeline:
    """Orchestrates sequential execution of generators and fires lifecycle events."""

    def __init__(self, steps: List[PipelineStep], event_bus: EventBusService) -> None:
        """
        Initializes the pipeline with steps and event bus.

        Args:
            steps (List[PipelineStep]): Steps to execute in order.
            event_bus (EventBusService): Core system event bus.
        """
        self.steps = steps
        self.event_bus = event_bus

    def execute(self, context: ImplementationContext) -> None:
        """
        Runs all registered steps sequentially, tracking progress.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Starting implementation pipeline...")
        context.progress_percentage = 0.0

        # Publish started event
        self.event_bus.publish(
            Event(
                event_type="developer.started",
                data={
                    "project_id": context.architecture.project_id,
                    "workspace": context.workspace,
                },
            )
        )

        total_steps = len(self.steps)

        for i, step in enumerate(self.steps):
            context.logger.info(f"Running step: {step.name}")

            try:
                # Store the number of files before running step to see if any new files were added
                pre_file_count = len(context.generated_files)

                step.run(context)

                # Track any new generated files and publish file_generated events
                post_files = context.generated_files[pre_file_count:]
                for gen_file in post_files:
                    self.event_bus.publish(
                        Event(
                            event_type="developer.file_generated",
                            data={
                                "project_id": context.architecture.project_id,
                                "path": gen_file.path,
                                "file_type": gen_file.file_type,
                            },
                        )
                    )

                # Update progress
                context.progress_percentage = round(((i + 1) / total_steps) * 100, 1)
                context.logger.info(
                    f"Step '{step.name}' completed. Progress: {context.progress_percentage}%"
                )

                # Publish progress updated event
                self.event_bus.publish(
                    Event(
                        event_type="developer.progress_updated",
                        data={
                            "project_id": context.architecture.project_id,
                            "progress": context.progress_percentage,
                            "last_completed_step": step.name,
                        },
                    )
                )

            except Exception as e:
                context.logger.error(f"Error in step '{step.name}': {e}", exc_info=True)
                self.event_bus.publish(
                    Event(
                        event_type="developer.failed",
                        data={
                            "project_id": context.architecture.project_id,
                            "failed_step": step.name,
                            "error": str(e),
                        },
                    )
                )
                raise
