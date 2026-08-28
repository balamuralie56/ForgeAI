"""
Validator verifying structural plan and workspace integrity before reviewing.
"""

from pathlib import Path
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.reviewer.exceptions import ReviewerValidationError


class ReviewerValidator:
    """Validates pipeline parameters and ensures files exist prior to review operations."""

    def validate(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        workspace_path: str,
    ) -> None:
        """
        Validates the code review inputs.

        Raises:
            ReviewerValidationError: If inputs are invalid or path is inaccessible.
        """
        if not plan:
            raise ReviewerValidationError("Project plan cannot be None.")

        if not spec:
            raise ReviewerValidationError("Architecture specification cannot be None.")

        if not report:
            raise ReviewerValidationError("Implementation report cannot be None.")

        if not workspace_path:
            raise ReviewerValidationError("Workspace path must be specified.")

        workspace = Path(workspace_path)
        if not workspace.exists() or not workspace.is_dir():
            raise ReviewerValidationError(
                f"Workspace path does not exist or is not a directory: {workspace_path}"
            )
