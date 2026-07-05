"""
Frontend Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate


class FrontendGenerator(PipelineStep):
    """Generates frontend web templates, views, and UI script/stylesheet files."""

    @property
    def name(self) -> str:
        return "Frontend Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the frontend generator, extending generated files in-context.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Executing frontend generator step...")
        files = load_prompt_and_generate(context, "frontend", "frontend")
        context.generated_files.extend(files)
