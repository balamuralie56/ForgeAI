"""
Regression Test Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class RegressionTestGenerator(TestPipelineStep):
    """Generates regression test suites checking logic boundaries and consistency."""

    @property
    def name(self) -> str:
        return "Regression Test Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "regression", "regression")
        context.generated_test_files.extend(files)
