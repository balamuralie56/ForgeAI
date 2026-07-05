"""
Coverage Report Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class CoverageReportGenerator(TestPipelineStep):
    """Generates expected test coverage plans and threshold goals."""

    @property
    def name(self) -> str:
        return "Coverage Report Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "coverage", "coverage")
        context.generated_test_files.extend(files)
