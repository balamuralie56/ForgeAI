"""
Durable workspace writer for code review reports (Markdown, JSON, manifest).
"""

import json
import logging
from pathlib import Path
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from forge_plugins.reviewer.models import ReviewReport, ReviewManifest
from forge_plugins.reviewer.exceptions import ReviewerWriteError

logger = logging.getLogger("ForgeAI.Plugins.Reviewer.Writer")


class ReviewerWorkspaceWriter:
    """Atomically writes code review findings and reports to target workspaces."""

    def __init__(self, event_bus: EventBusService) -> None:
        self.event_bus = event_bus

    def write_reports(
        self,
        workspace: str,
        report: ReviewReport,
        manifest: ReviewManifest,
    ) -> None:
        """Writes all output review formats to the workspace root."""
        workspace_path = Path(workspace)
        if not workspace_path.exists():
            raise ReviewerWriteError(f"Workspace path does not exist: {workspace}")

        try:
            json_report_path = workspace_path / "review_report.json"
            json_report_path.write_text(
                json.dumps(report.to_dict(), indent=4), encoding="utf-8"
            )

            md_summary_path = workspace_path / "review_summary.md"
            md_summary_path.write_text(report.summary, encoding="utf-8")

            manifest_path = workspace_path / "review_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=4), encoding="utf-8"
            )

            logger.info(f"Successfully wrote code review deliverables to {workspace}")

            self.event_bus.publish(
                Event(
                    event_type="reviewer.report.generated",
                    data={
                        "project_id": report.project_id,
                        "quality_score": report.quality_score,
                        "findings_count": len(report.findings),
                    },
                )
            )

        except Exception as e:
            logger.error(f"Failed to write review reports: {e}", exc_info=True)
            raise ReviewerWriteError(f"Failed writing review files: {e}") from e
