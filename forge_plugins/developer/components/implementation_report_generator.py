"""
Implementation Report Generator component for the Developer Plugin.
"""

from typing import Dict, List
from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.models import GeneratedFile


class ImplementationReportGenerator(PipelineStep):
    """Compiles execution statistics and generates a markdown summary report."""

    @property
    def name(self) -> str:
        return "Implementation Report Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the report generator, compiling generated files metadata into a summary report.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Executing implementation report generator step...")

        # Count files by type
        stats: Dict[str, int] = {}
        for gf in context.generated_files:
            stats[gf.file_type] = stats.get(gf.file_type, 0) + 1

        total_files = len(context.generated_files)

        # Build markdown report
        lines = [
            f"# Implementation Report: {context.project_plan.goal.goal}",
            "",
            "## Executive Summary",
            f"Autonomous software development completed for Project **{context.architecture.project_id}**.",
            "",
            "### Generation Summary Statistics",
            f"- **Total Files Generated**: {total_files}",
        ]

        for ft, count in sorted(stats.items()):
            lines.append(f"- **{ft.capitalize()} Files**: {count}")

        lines.extend(
            [
                "",
                "## Generated File Registry",
                "Below is the complete list of files generated:",
                "",
                "| Path | File Type | Size (Bytes) |",
                "| --- | --- | --- |",
            ]
        )

        for gf in context.generated_files:
            lines.append(
                f"| `{gf.path}` | {gf.file_type} | {len(gf.content.encode('utf-8'))} |"
            )

        lines.extend(self._validation_section(context))

        lines.extend(
            [
                "",
                "---",
                "*Report generated automatically by the ForgeAI Developer Plugin pipeline.*",
            ]
        )

        content = "\n".join(lines)

        # Append the report as a generated file in memory
        context.generated_files.append(
            GeneratedFile(
                path="implementation_report.md",
                content=content,
                file_type="report",
            )
        )

    @staticmethod
    def _validation_section(context: ImplementationContext) -> List[str]:
        """Markdown lines describing the code validation outcome, if it ran."""
        result = context.validation
        if result is None:
            return []

        lines = [
            "",
            "## Code Validation",
            f"- **Status**: {result.status.value}",
            f"- **Files Checked**: {result.checked_files}",
            f"- **Errors**: {len(result.errors)}",
            f"- **Warnings**: {len(result.warnings)}",
        ]
        if not result.issues:
            lines.extend(["", "No problems found."])
            return lines

        lines.extend(
            [
                "",
                "| Severity | Check | Location | Problem |",
                "| --- | --- | --- | --- |",
            ]
        )
        for issue in result.issues:
            location = (
                f"`{issue.path}:{issue.line}`" if issue.line else f"`{issue.path}`"
            )
            message = issue.message.replace("|", "\\|")
            lines.append(
                f"| {issue.severity.value} | {issue.check} | {location} | {message} |"
            )
        return lines
