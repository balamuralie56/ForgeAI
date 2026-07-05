"""
Dependency Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate


class DependencyGenerator(PipelineStep):
    """Generates package dependency definition files."""

    @property
    def name(self) -> str:
        return "Dependency Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the dependency generator, extending generated files in-context.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Executing dependency generator step...")
        files = load_prompt_and_generate(context, "dependency", "dependency")
        context.generated_files.extend(files)
