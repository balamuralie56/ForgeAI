"""
Implementation Report Generator component for the Developer Plugin.
"""

from typing import Dict
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
                "Below is the complete list of files successfully built:",
                "",
                "| Path | File Type | Size (Bytes) |",
                "| --- | --- | --- |",
            ]
        )

        for gf in context.generated_files:
            lines.append(
                f"| `{gf.path}` | {gf.file_type} | {len(gf.content.encode('utf-8'))} |"
            )

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
