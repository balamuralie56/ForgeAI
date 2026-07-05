"""
Input validation and verification helpers for the Documentation Plugin.
"""

import logging
from pathlib import Path
from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.models import TestReport
from ..exceptions import DocValidationError

logger = logging.getLogger("ForgeAI.Plugins.Documentation.Validators")


class DocValidator:
    """
    Validates completeness of input artifacts and integrity of target directories.
    """

    def validate(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        report: ImplementationReport,
        test_report: TestReport,
        workspace_path: str,
    ) -> None:
        """
        Runs validation checks on the supplied planning, architecture, developer, and tester models.

        Args:
            plan (ProjectPlan): The project requirements plan.
            spec (ArchitectureSpecification): The software architecture spec.
            report (ImplementationReport): The codebase files report.
            test_report (TestReport): The verification tests report.
            workspace_path (str): The destination directory path.

        Raises:
            DocValidationError: If any validation checks fail.
        """
        logger.info("Starting input specifications validation checks...")

        if not plan:
            raise DocValidationError("Project Plan is missing or None.")
        if not plan.goal or not plan.goal.goal:
            raise DocValidationError("Project Plan does not define a valid goal.")

        if not spec:
            raise DocValidationError("Architecture Specification is missing or None.")
        if not spec.project_id:
            raise DocValidationError(
                "Architecture Specification does not define a project ID."
            )

        if not report:
            raise DocValidationError("Implementation Report is missing or None.")
        if not report.files:
            raise DocValidationError(
                "Implementation Report contains no generated source files."
            )

        if not test_report:
            raise DocValidationError("Test Report is missing or None.")

        # Validate target workspace path
        if not workspace_path:
            raise DocValidationError("Target workspace path is empty.")

        path = Path(workspace_path)
        if not path.exists() or not path.is_dir():
            raise DocValidationError(
                f"Target workspace directory does not exist or is not a directory: {workspace_path}"
            )

        logger.info("Input specifications validation checks completed successfully.")
