"""
Integration Test Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class IntegrationTestGenerator(TestPipelineStep):
    """Generates integration tests verifying sub-system boundaries."""

    @property
    def name(self) -> str:
        return "Integration Test Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "integration", "integration")
        context.generated_test_files.extend(files)
