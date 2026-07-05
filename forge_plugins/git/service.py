"""
Service definitions and implementation for the ForgeAI Git Plugin.
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
from forge_plugins.documentation.models import DocumentationReport

from .models import GitReport
from .exceptions import GitError, GitValidationError, GitOperationError
from .validators.git_validator import GitValidator
from .utils.git_operations import GitOperations
from .utils.git_pipeline import GitContext, GitPipeline
from .components import (
    BranchStep,
    CommitStep,
    SemverStep,
    TagStep,
    ChangelogStep,
    GitHubPRStep,
    CiManifestStep,
)

logger = logging.getLogger("ForgeAI.Plugins.Git")


class GitService(ABC):
    """
    Interface for the Git Plugin service.
    """

    @abstractmethod
    def commit_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        test_report: TestReport,
        doc_report: DocumentationReport,
    ) -> GitReport:
        """
        Executes the full git delivery pipeline for a generated project.

        Args:
            plan (ProjectPlan): The project requirements plan.
            spec (ArchitectureSpecification): The software architecture specification.
            implementation_report (ImplementationReport): The implementation output report.
            test_report (TestReport): The test execution report.
            doc_report (DocumentationReport): The documentation generation report.

        Returns:
            GitReport: The compiled git delivery report.
        """
        pass


class ForgeAIGit(GitService):
    """
    Concrete implementation of the Git service running the full delivery pipeline.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """Initialises the git service resolving all kernel dependencies."""
        self._model_router = registry.resolve(ModelRouterService)  # type: ignore[type-abstract]
        self._event_bus = registry.resolve(EventBusService)  # type: ignore[type-abstract]
        self._memory = registry.resolve(MemoryService)  # type: ignore[type-abstract]
        self._config = registry.resolve(ConfigurationService)  # type: ignore[type-abstract]
        self.validator = GitValidator()

    def commit_project(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        test_report: TestReport,
        doc_report: DocumentationReport,
    ) -> GitReport:
        """
        Runs the full git delivery pipeline:
        validation → branch → commit → semver → tag → changelog → GitHub PR → CI manifest → memory → events.
        """
        project_id = spec.project_id if spec else "unknown"
        logger.info(f"Initiating Git delivery pipeline for project: '{project_id}'")

        # 1. Resolve workspace path
        workspace_path = ""
        try:
            settings = self._config.get_system_settings()
            workspace_path = settings.workspace_dir
        except Exception as exc:
            raise GitError(f"Failed to resolve system workspace settings: {exc}") from exc

        # 2. Resolve full configuration
        try:
            full_config = self._config.get_full_config()
        except Exception as exc:
            raise GitError(f"Failed to resolve full system configuration: {exc}") from exc

        # 3. Run pre-flight validation
        try:
            self.validator.validate(
                plan, spec, implementation_report, test_report, doc_report,
                workspace_path, full_config,
            )
        except GitValidationError as val_err:
            logger.error(f"Git pre-flight validation failed: {val_err}")
            self._event_bus.publish(
                Event(
                    event_type="git.validation_failed",
                    data={"project_id": project_id, "error": str(val_err)},
                )
            )
            raise

        # 4. Build git operations adapter
        git_ops = GitOperations(workspace_path)

        # 5. Setup pipeline context
        context = GitContext(
            plan=plan,
            spec=spec,
            implementation_report=implementation_report,
            test_report=test_report,
            doc_report=doc_report,
            workspace=workspace_path,
            git_ops=git_ops,
            model_router=self._model_router,
            event_bus=self._event_bus,
            configuration=full_config,
            logger=logger,
        )

        # 6. Build and run the pipeline
        steps = [
            BranchStep(),
            CommitStep(),
            SemverStep(),
            TagStep(),
            ChangelogStep(),
            GitHubPRStep(),
            CiManifestStep(),
        ]
        pipeline = GitPipeline(steps, self._event_bus)

        try:
            pipeline.run(context)
        except GitOperationError as op_err:
            logger.error(f"Git operation failed during pipeline execution: {op_err}")
            self._event_bus.publish(
                Event(
                    event_type="git.operation_failed",
                    data={"project_id": project_id, "error": str(op_err)},
                )
            )
            raise
        except Exception as err:
            logger.error(f"Unexpected error in git delivery pipeline: {err}")
            self._event_bus.publish(
                Event(
                    event_type="git.operation_failed",
                    data={"project_id": project_id, "error": str(err)},
                )
            )
            raise GitOperationError(
                f"Git delivery pipeline encountered an unexpected error: {err}"
            ) from err

        # 7. Build the git report
        summary_parts = [f"Branch: {context.branch}"]
        if context.semver:
            summary_parts.append(
                f"Version: {context.semver.current} → {context.semver.recommended}"
            )
        if context.tags:
            summary_parts.append(f"Tags: {', '.join(t.name for t in context.tags)}")
        if context.pr:
            summary_parts.append(f"PR: {context.pr.url}")

        git_report = GitReport(
            project_id=project_id,
            commits=context.commits,
            tags=context.tags,
            semver=context.semver,
            pr=context.pr,
            changelog=context.changelog,
            ci_manifest=context.ci_manifest,
            status="SUCCESS",
            summary=" | ".join(summary_parts),
        )

        # 8. Persist report to memory
        try:
            report_dict = git_report.to_dict()
            self._memory.runtime.set_project_state("git_report", report_dict)
            self._memory.project.set_metadata("git_report", report_dict)
        except Exception as mem_err:
            logger.error(
                f"Failed to persist git report to memory registries: {mem_err}"
            )

        # 9. Publish completion event
        self._event_bus.publish(
            Event(
                event_type="git.completed",
                data={
                    "project_id": project_id,
                    "commits": len(context.commits),
                    "tags": len(context.tags),
                    "version": context.semver.recommended if context.semver else "N/A",
                },
            )
        )

        logger.info(
            f"Git delivery pipeline completed successfully for project '{project_id}'."
        )
        return git_report
