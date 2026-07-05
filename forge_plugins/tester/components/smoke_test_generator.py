"""
Smoke Test Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class SmokeTestGenerator(TestPipelineStep):
    """Generates smoke tests verifying deployment and boot-up sanity."""

    @property
    def name(self) -> str:
        return "Smoke Test Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "smoke", "smoke")
        context.generated_test_files.extend(files)
