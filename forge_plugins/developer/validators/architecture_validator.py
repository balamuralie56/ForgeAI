"""
Input validation for the Developer Plugin.
"""

import logging
from pathlib import Path
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.exceptions import DeveloperValidationError

logger = logging.getLogger("ForgeAI.Plugins.Developer.Validators")


class ArchitectureValidator:
    """Validates the input ProjectPlan and ArchitectureSpecification."""

    def validate(
        self, plan: ProjectPlan, spec: ArchitectureSpecification, workspace_path: str
    ) -> None:
        """
        Validates the planning and architectural design inputs.

        Args:
            plan (ProjectPlan): The decomposed project plan.
            spec (ArchitectureSpecification): The designed software architecture specification.
            workspace_path (str): The target output directory path.

        Raises:
            DeveloperValidationError: If inputs are invalid or insufficient.
        """
        logger.info("Validating developer input specs...")

        if not plan:
            raise DeveloperValidationError("Project plan is missing.")

        if not plan.goal or not plan.goal.goal:
            raise DeveloperValidationError("Project plan has no valid goal title.")

        if not spec:
            raise DeveloperValidationError("Architecture specification is missing.")

        if not spec.project_id:
            raise DeveloperValidationError(
                "Architecture specification has no project_id."
            )

        if not spec.directory_structure:
            raise DeveloperValidationError(
                "Architecture specification does not define a directory structure."
            )

        if not workspace_path:
            raise DeveloperValidationError("Workspace target path is empty.")

        # Ensure the parent directory of workspace exists or can be written to
        try:
            p = Path(workspace_path)
            # Create if it doesn't exist, to check write capabilities
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise DeveloperValidationError(
                f"Workspace path '{workspace_path}' is invalid or unwritable: {e}"
            ) from e

        logger.info("Developer spec validation completed successfully.")
