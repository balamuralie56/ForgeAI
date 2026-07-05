"""
API Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate


class APIGenerator(PipelineStep):
    """Generates API route, payload validation, and controller files."""

    @property
    def name(self) -> str:
        return "API Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the API generator, extending generated files in-context.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        context.logger.info("Executing API generator step...")
        files = load_prompt_and_generate(context, "api", "api")
        context.generated_files.extend(files)
