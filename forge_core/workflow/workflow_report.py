"""
Report generator for orchestrated workflows producing JSON reports and Markdown summaries.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict
from .models import Workflow


class WorkflowReportGenerator:
    """
    Constructs and writes execution reports for finished or aborted workflows.
    """

    @classmethod
    def generate_report(cls, workflow: Workflow) -> Dict[str, Any]:
        """
        Generates a dictionary report from a workflow state.
        """
        total_duration = workflow.updated_at - workflow.created_at
        stages_report = []

        for stage in workflow.stages:
            duration = 0.0
            if stage.started_at and stage.completed_at:
                duration = stage.completed_at - stage.started_at
            elif stage.started_at:
                duration = time.time() - stage.started_at

            stages_report.append(
                {
                    "name": stage.name,
                    "status": stage.status.value,
                    "duration_seconds": round(duration, 2),
                    "error": stage.error,
                }
            )

        return {
            "workflow_id": workflow.id,
            "name": workflow.name,
            "type": workflow.type.value,
            "status": workflow.state.value,
            "progress": workflow.progress,
            "total_duration_seconds": round(total_duration, 2),
            "stages": stages_report,
            "created_at": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(workflow.created_at)
            ),
            "updated_at": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(workflow.updated_at)
            ),
        }

    @classmethod
    def generate_markdown_summary(cls, report_data: Dict[str, Any]) -> str:
        """
        Constructs a clean Markdown representation of the execution run.
        """
        status_emoji = {
            "COMPLETED": "✅ SUCCESS",
            "FAILED": "❌ FAILED",
            "CANCELLED": "⏹️ CANCELLED",
            "RUNNING": "⏳ RUNNING",
            "WAITING": "⏸️ WAITING",
            "PENDING": "📭 PENDING",
        }.get(report_data["status"], report_data["status"])

        md = []
        md.append(f"# ForgeAI Workflow Summary: {report_data['name']}")
        md.append(f"**Workflow ID:** `{report_data['workflow_id']}`")
        md.append(f"**Workflow Type:** `{report_data['type']}`")
        md.append(f"**Overall Status:** {status_emoji}")
        md.append(f"**Progress:** `{report_data['progress']}%`")
        md.append(
            f"**Total Execution Time:** `{report_data['total_duration_seconds']}s`"
        )
        md.append(f"**Created At:** `{report_data['created_at']}`")
        md.append(f"**Updated At:** `{report_data['updated_at']}`")
        md.append("\n## Stage Executions\n")
        md.append("| Stage Name | Status | Duration | Error Info |")
        md.append("| :--- | :--- | :--- | :--- |")

        for stage in report_data["stages"]:
            err_info = f"`{stage['error']}`" if stage["error"] else "-"
            md.append(
                f"| {stage['name']} | {stage['status']} | {stage['duration_seconds']}s | {err_info} |"
            )

        return "\n".join(md)

    @classmethod
    def write_reports(cls, workspace_dir: str, workflow: Workflow) -> Dict[str, Any]:
        """
        Writes the JSON report and Markdown summary to the target workspace directory.
        """
        report_data = cls.generate_report(workflow)
        md_content = cls.generate_markdown_summary(report_data)

        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)

        json_path = workspace_path / "workflow_report.json"
        md_path = workspace_path / "workflow_summary.md"

        json_path.write_text(json.dumps(report_data, indent=4), encoding="utf-8")
        md_path.write_text(md_content, encoding="utf-8")

        return report_data
