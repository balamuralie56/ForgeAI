"""
Configuration Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate
from forge_plugins.developer.utils.stack_templates import (
    detect_python_stack,
    generate_configuration_files,
)


class ConfigurationGenerator(PipelineStep):
    """Generates application/framework configuration settings files."""

    @property
    def name(self) -> str:
        return "Configuration Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the configuration generator, extending generated files in-context.
        Skips the LLM call entirely for a confidently-detected Python stack -
        the config module just needs to read back whatever variables the
        environment generator defined, not a judgment call. Falls back to LLM
        generation unchanged for anything else.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        stack = detect_python_stack(context.architecture)
        if stack is not None:
            context.logger.info(
                "Configuration generator: templating src/config.py for detected "
                f"Python stack (framework={stack.web_framework or 'none'}, "
                f"database={stack.has_database}) - no LLM call needed."
            )
            context.generated_files.extend(generate_configuration_files(stack))
            return

        context.logger.info("Executing configuration generator step...")
        files = load_prompt_and_generate(context, "configuration", "configuration")
        context.generated_files.extend(files)
