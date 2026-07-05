"""
Fixture Generator compilation step for the Tester Plugin.
"""

from forge_plugins.tester.utils.test_pipeline import TestContext, TestPipelineStep
from forge_plugins.tester.utils.prompt_helper import load_prompt_and_generate


class FixtureGenerator(TestPipelineStep):
    """Generates test fixtures and conftest files."""

    @property
    def name(self) -> str:
        return "Fixture Generator"

    def run(self, context: TestContext) -> None:
        files = load_prompt_and_generate(context, "fixture", "fixture")
        context.generated_test_files.extend(files)
