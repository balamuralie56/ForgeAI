"""
Validator verifying structural plan and workspace integrity before scanning.
"""

from pathlib import Path
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.security.exceptions import SecurityValidationError


class SecurityValidator:
    """
    Validates pipeline parameters and ensures files exist prior to audit operations.
    """

    def validate(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        workspace_path: str,
    ) -> None:
        """
        Validates the security scanning inputs.

        Raises:
            SecurityValidationError: If inputs are invalid or path is inaccessible.
        """
        if not plan:
            raise SecurityValidationError("Project plan cannot be None.")

        if not spec:
            raise SecurityValidationError("Architecture specification cannot be None.")

        if not report:
            raise SecurityValidationError("Implementation report cannot be None.")

        if not workspace_path:
            raise SecurityValidationError("Workspace path must be specified.")

        workspace = Path(workspace_path)
        if not workspace.exists() or not workspace.is_dir():
            raise SecurityValidationError(
                f"Workspace path does not exist or is not a directory: {workspace_path}"
            )
