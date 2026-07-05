"""
Unit Test Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class UnitTestGenerator(TestPipelineStep):
    """Generates unit tests verifying specific functions and class boundaries."""

    @property
    def name(self) -> str:
        return "Unit Test Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "unit", "unit")
        context.generated_test_files.extend(files)
