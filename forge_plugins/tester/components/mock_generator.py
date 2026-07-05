"""
Mock Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class MockGenerator(TestPipelineStep):
    """Generates mock classes and test stubs from implemented code assets."""

    @property
    def name(self) -> str:
        return "Mock Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "mock", "mock")
        context.generated_test_files.extend(files)
