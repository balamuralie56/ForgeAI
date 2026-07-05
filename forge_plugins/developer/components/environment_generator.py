"""
Environment Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate


class EnvironmentGenerator(PipelineStep):
    """Generates environment template and configuration files."""

    @property
    def name(self) -> str:
        return "Environment Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the environment generator, extending generated files in-context.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Executing environment generator step...")
        files = load_prompt_and_generate(context, "environment", "environment")
        context.generated_files.extend(files)
