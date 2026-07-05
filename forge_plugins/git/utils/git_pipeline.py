"""
Pipeline execution orchestrator for the Git Plugin — sequences and runs all git steps.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_core.model_router.service import ModelRouterService
from forge_core.configuration.models import ForgeConfig
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.models import TestReport
from forge_plugins.documentation.models import DocumentationReport

from ..models import GitCommit, GitTag, SemverBump, GitHubPR
from .git_operations import GitOperations

logger = logging.getLogger("ForgeAI.Plugins.Git.Utils")


class GitContext:
    """
    Shared context object passed through every step of the Git pipeline.
    Carries all input artifacts and accumulates mutable output state.
    """

    def __init__(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        test_report: TestReport,
        doc_report: DocumentationReport,
        workspace: str,
        git_ops: GitOperations,
        model_router: ModelRouterService,
        event_bus: EventBusService,
        configuration: ForgeConfig,
        logger: logging.Logger,
    ) -> None:
        """Initialises the shared git pipeline context."""
        self.plan = plan
        self.spec = spec
        self.implementation_report = implementation_report
        self.test_report = test_report
        self.doc_report = doc_report
        self.workspace = workspace
        self.git_ops = git_ops
        self.model_router = model_router
        self.event_bus = event_bus
        self.configuration = configuration
        self.logger = logger

        # Mutable pipeline output state
        self.branch: str = ""
        self.commits: List[GitCommit] = []
        self.tags: List[GitTag] = []
        self.semver: Optional[SemverBump] = None
        self.pr: Optional[GitHubPR] = None
        self.changelog: str = ""
        self.ci_manifest: Dict[str, Any] = {}
        self.progress_percentage: float = 0.0


class GitPipelineStep(ABC):
    """Abstract base class for a single step in the Git delivery pipeline."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique human-readable identifier for this pipeline step."""
        pass

    @abstractmethod
    def run(self, context: GitContext) -> None:
        """
        Executes the step logic against the shared context.

        Args:
            context (GitContext): The shared pipeline context.
        """
        pass


class GitPipeline:
    """
    Sequences and executes GitPipelineSteps, emitting lifecycle events for each step.
    """

    def __init__(
        self, steps: List[GitPipelineStep], event_bus: EventBusService
    ) -> None:
        """
        Initialises the pipeline.

        Args:
            steps (List[GitPipelineStep]): Ordered list of steps to execute.
            event_bus (EventBusService): The system event bus.
        """
        self.steps = steps
        self.event_bus = event_bus

    def run(self, context: GitContext) -> None:
        """
        Executes each step, updates progress percentage, and publishes step events.

        Args:
            context (GitContext): The shared pipeline context.
        """
        total_steps = len(self.steps)
        if total_steps == 0:
            return

        for index, step in enumerate(self.steps):
            context.logger.info(f"Running git step: {step.name}")

            self.event_bus.publish(
                Event(
                    event_type="git.step_started",
                    data={
                        "step_name": step.name,
                        "project_id": context.spec.project_id,
                    },
                )
            )

            step.run(context)

            context.progress_percentage = ((index + 1) / total_steps) * 100.0
            context.logger.info(
                f"Git step '{step.name}' completed. Progress: {context.progress_percentage:.1f}%"
            )

            self.event_bus.publish(
                Event(
                    event_type="git.step_completed",
                    data={
                        "step_name": step.name,
                        "project_id": context.spec.project_id,
                        "progress": context.progress_percentage,
                    },
                )
            )
