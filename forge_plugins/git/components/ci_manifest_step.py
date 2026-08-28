"""
CiManifestStep — writes ci_manifest.json to the workspace root for CI/CD pipeline consumption.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..utils.git_pipeline import GitContext, GitPipelineStep

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")

_CI_MANIFEST_FILENAME = "ci_manifest.json"


class CiManifestStep(GitPipelineStep):
    """
    Compiles and writes a ci_manifest.json file to the workspace root.
    The manifest aggregates key pipeline statistics for downstream CI/CD consumption.
    """

    @property
    def name(self) -> str:
        return "CI Manifest Step"

    def run(self, context: GitContext) -> None:
        """
        Builds the CI manifest dictionary from pipeline context state and writes it to disk.

        Args:
            context (GitContext): The shared pipeline context.
        """
        context.logger.info("Compiling CI manifest...")

        sha = ""
        if context.commits:
            sha = context.commits[-1].sha
        else:
            try:
                sha = context.git_ops.rev_parse("HEAD")
            except Exception:
                sha = "unknown"

        version = context.semver.recommended if context.semver else "0.0.0"
        tag_name = f"v{version}"

        test_status = getattr(context.test_report, "status", "UNKNOWN")
        doc_count = len(context.doc_report.doc_files)

        # Attempt to read coverage from test report summary
        coverage = self._extract_coverage(context)

        security_status = "N/A"
        security_score = 100.0
        risk_score = 0.0
        if context.security_report:
            security_status = getattr(context.security_report, "status", "UNKNOWN")
            security_score = getattr(context.security_report, "security_score", 100.0)
            risk_score = getattr(context.security_report, "risk_score", 0.0)

        manifest: dict = {
            "project_id": context.spec.project_id,
            "branch": context.branch,
            "version": version,
            "tag": tag_name,
            "commit_sha": sha,
            "test_status": test_status,
            "coverage": coverage,
            "security_status": security_status,
            "security_score": security_score,
            "security_risk_score": risk_score,
            "implementation_files": len(context.implementation_report.files),
            "test_files": len(context.test_report.test_files),
            "docs_generated": doc_count,
            "commits": len(context.commits),
            "github_pr": context.pr.url if context.pr else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        context.ci_manifest = manifest

        manifest_path = Path(context.workspace) / _CI_MANIFEST_FILENAME
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            context.logger.info(f"ci_manifest.json written to: {manifest_path}")
        except Exception as exc:
            context.logger.error(f"Failed to write ci_manifest.json: {exc}")
            raise

    def _extract_coverage(self, context: GitContext) -> str:
        """
        Attempts to extract coverage percentage from the test report summary.
        Returns 'N/A' if not found.

        Args:
            context (GitContext): The shared pipeline context.

        Returns:
            str: Coverage percentage string, e.g. '91%'.
        """
        summary = getattr(context.test_report, "summary", "") or ""
        import re

        match = re.search(r"(\d+(?:\.\d+)?)\s*%", summary)
        if match:
            return f"{match.group(1)}%"
        return "N/A"
