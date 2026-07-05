"""
Implementation validation logic for the ForgeAI Tester Plugin.
"""

from pathlib import Path
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.exceptions import TestValidationError


class ImplementationValidator:
    """
    Validates input models and the workspace state before running test generation.
    """

    def validate(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        workspace_dir: str,
    ) -> None:
        """
        Validates that planning, architecture, and developer outputs exist and are correct,
        and checks that the workspace is correctly set up.

        Args:
            plan (ProjectPlan): Decomposed project plan.
            spec (ArchitectureSpecification): Designed software architecture spec.
            report (ImplementationReport): Developer pipeline output report.
            workspace_dir (str): Root of the target workspace.

        Raises:
            TestValidationError: If validations fail.
        """
        if not plan or not plan.goal.goal:
            raise TestValidationError("ProjectPlan or project goal is missing.")

        if not spec or not spec.project_id:
            raise TestValidationError(
                "ArchitectureSpecification or Project ID is missing."
            )

        if not report or not report.files:
            raise TestValidationError(
                "ImplementationReport is missing or contains no generated files."
            )

        if not workspace_dir:
            raise TestValidationError("Workspace directory path is empty.")

        workspace_path = Path(workspace_dir)
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise TestValidationError(
                f"Target workspace directory does not exist or is not a directory: {workspace_dir}"
            )

        # Confirm that at least one of the files in the report exists in the workspace
        file_found = False
        for gf in report.files:
            if gf.file_type != "report":
                filepath = workspace_path / gf.path
                if filepath.exists():
                    file_found = True
                    break

        if not file_found:
            raise TestValidationError(
                f"Generated source files from implementation report were not found in workspace: {workspace_dir}"
            )
