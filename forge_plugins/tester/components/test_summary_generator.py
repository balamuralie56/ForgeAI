"""
Test Summary Generator step for the Tester Plugin.
Compiles a report summarizing all generated test suites and files.
"""

from typing import Dict
from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.models import GeneratedTestFile


class TestSummaryGenerator(TestPipelineStep):
    """Compiles the final markdown test report for the generated test suites."""

    @property
    def name(self) -> str:
        return "Test Summary Generator"

    def run(self, context: TestContext) -> None:
        # Group generated files by type for summary statistics
        stats: Dict[str, int] = {}
        for tf in context.generated_test_files:
            stats[tf.test_type] = stats.get(tf.test_type, 0) + 1

        total_files = len(context.generated_test_files)

        # Build markdown report
        markdown = []
        markdown.append(
            f"# Test Implementation Report: {context.architecture.project_id}\n"
        )
        markdown.append("## Executive Summary")
        markdown.append("Autonomous test suite generation completed successfully.")
        markdown.append(f"- **Total Test Files Generated**: {total_files}\n")

        markdown.append("### Statistics by Test Type")
        for t, count in sorted(stats.items()):
            markdown.append(f"- **{t.capitalize()} Files**: {count}")
        markdown.append("")

        markdown.append("## Generated Test File Registry")
        markdown.append("| Path | Test Type | Size (Bytes) |")
        markdown.append("| --- | --- | --- |")
        for tf in context.generated_test_files:
            size = len(tf.content.encode("utf-8"))
            markdown.append(f"| `{tf.path}` | {tf.test_type} | {size} |")
        markdown.append("")

        markdown.append("---\n*Report compiled by the ForgeAI Tester Plugin.*")

        report_content = "\n".join(markdown)
        report_file = GeneratedTestFile(
            path="tests/test_report.md",
            content=report_content,
            test_type="summary",
        )
        context.generated_test_files.append(report_file)
