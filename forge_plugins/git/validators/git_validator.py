"""
Input validation for the Git Plugin pre-flight checks.
"""

import logging
import shutil
from typing import Optional, Any
from pathlib import Path

from forge_plugins.planner.models import ProjectPlan
from forge_plugins.architect.models import ArchitectureSpecification
from forge_plugins.developer.models import ImplementationReport
from forge_plugins.tester.models import TestReport
from forge_plugins.documentation.models import DocumentationReport
from forge_core.configuration.models import ForgeConfig

from ..exceptions import GitValidationError

logger = logging.getLogger("ForgeAI.Plugins.Git.Validators")


class GitValidator:
    """
    Validates all pre-flight conditions required by the Git Plugin before any git operations begin.
    """

    def validate(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        test_report: TestReport,
        doc_report: DocumentationReport,
        workspace_path: str,
        configuration: ForgeConfig,
        security_report: Optional[Any] = None,
    ) -> None:
        """
        Runs all pre-flight validation checks.

        Args:
            plan (ProjectPlan): The project requirements plan.
            spec (ArchitectureSpecification): The architecture specification.
            implementation_report (ImplementationReport): The implementation output.
            test_report (TestReport): The testing output.
            doc_report (DocumentationReport): The documentation output.
            workspace_path (str): Path to the target project workspace.
            configuration (ForgeConfig): The full system configuration.

        Raises:
            GitValidationError: If any check fails.
        """
        logger.info("Starting Git Plugin pre-flight validation...")

        self._validate_artifacts(
            plan, spec, implementation_report, test_report, doc_report
        )
        self._validate_workspace(workspace_path)
        self._validate_git_binary()
        self._validate_github_config(configuration)
        self._validate_security_gates(configuration, security_report)

        logger.info("Git Plugin pre-flight validation completed successfully.")

    def _validate_artifacts(
        self,
        plan: ProjectPlan,
        spec: ArchitectureSpecification,
        implementation_report: ImplementationReport,
        test_report: TestReport,
        doc_report: DocumentationReport,
    ) -> None:
        """Validates that all upstream pipeline artifacts are present and non-empty."""
        if not plan:
            raise GitValidationError("ProjectPlan is missing or None.")
        if not plan.goal or not plan.goal.goal:
            raise GitValidationError("ProjectPlan does not define a valid goal.")

        if not spec:
            raise GitValidationError("ArchitectureSpecification is missing or None.")
        if not spec.project_id:
            raise GitValidationError(
                "ArchitectureSpecification does not define a project_id."
            )

        if not implementation_report:
            raise GitValidationError("ImplementationReport is missing or None.")
        if not implementation_report.files:
            raise GitValidationError(
                "ImplementationReport contains no generated source files."
            )

        if not test_report:
            raise GitValidationError("TestReport is missing or None.")

        if not doc_report:
            raise GitValidationError("DocumentationReport is missing or None.")

    def _validate_workspace(self, workspace_path: str) -> None:
        """Validates that the workspace path exists and is a directory."""
        if not workspace_path:
            raise GitValidationError("Workspace path is empty.")
        path = Path(workspace_path)
        if not path.exists() or not path.is_dir():
            raise GitValidationError(
                f"Workspace directory does not exist or is not a directory: {workspace_path}"
            )

    def _validate_git_binary(self) -> None:
        """Validates that the git binary is available on PATH."""
        if shutil.which("git") is None:
            raise GitValidationError(
                "git binary not found on PATH. Please install Git and ensure it is on PATH."
            )

    def _validate_github_config(self, configuration: ForgeConfig) -> None:
        """
        If GitHub mode is enabled in configuration, validates that the required
        token, owner, and repo settings are present.
        """
        git_config = getattr(configuration, "git", None)
        if git_config is None:
            return  # No git config block — GitHub mode is off

        github_enabled = getattr(git_config, "github_enabled", False)
        if not github_enabled:
            return

        token = getattr(git_config, "github_token", "")
        owner = getattr(git_config, "github_owner", "")
        repo = getattr(git_config, "github_repo", "")

        missing = []
        if not token:
            missing.append("github_token")
        if not owner:
            missing.append("github_owner")
        if not repo:
            missing.append("github_repo")

        if missing:
            raise GitValidationError(
                f"GitHub mode is enabled but the following config fields are missing: {', '.join(missing)}"
            )

    def _validate_security_gates(
        self, configuration: ForgeConfig, security_report: Optional[Any]
    ) -> None:
        """Enforces security quality release gates prior to committing/releasing."""
        if security_report is None:
            return

        sec_config = getattr(configuration, "security", {})
        if not sec_config or not sec_config.get("block_release", True):
            return

        max_critical = sec_config.get("max_critical", 0)
        max_high = sec_config.get("max_high", 2)
        max_risk = sec_config.get("max_risk_score", 30.0)

        findings = getattr(security_report, "findings", [])
        risk_score = getattr(security_report, "risk_score", 0.0)

        crit_count = sum(
            1
            for f in findings
            if getattr(f, "severity", None)
            and getattr(f, "severity").value == "CRITICAL"
        )
        high_count = sum(
            1
            for f in findings
            if getattr(f, "severity", None) and getattr(f, "severity").value == "HIGH"
        )

        if crit_count > max_critical:
            raise GitValidationError(
                f"Release blocked by Security Gate: {crit_count} Critical violations found (Max allowed: {max_critical})."
            )

        if high_count > max_high:
            raise GitValidationError(
                f"Release blocked by Security Gate: {high_count} High violations found (Max allowed: {max_high})."
            )

        if risk_score > max_risk:
            raise GitValidationError(
                f"Release blocked by Security Gate: Overall Risk Score {risk_score} exceeds limit of {max_risk}."
            )
