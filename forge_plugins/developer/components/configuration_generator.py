"""
Configuration Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate


class ConfigurationGenerator(PipelineStep):
    """Generates application/framework configuration settings files."""

    @property
    def name(self) -> str:
        return "Configuration Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the configuration generator, extending generated files in-context.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Executing configuration generator step...")
        files = load_prompt_and_generate(context, "configuration", "configuration")
        context.generated_files.extend(files)
