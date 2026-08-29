"""
Environment Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate
from forge_plugins.developer.utils.stack_templates import (
    detect_python_stack,
    generate_environment_files,
)


class EnvironmentGenerator(PipelineStep):
    """Generates environment template and configuration files."""

    @property
    def name(self) -> str:
        return "Environment Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the environment generator, extending generated files in-context.
        Skips the LLM call entirely for a confidently-detected Python stack -
        which env vars a project needs follows directly from whether it has a
        database or a web server, not a judgment call. Falls back to LLM
        generation unchanged for anything else.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        stack = detect_python_stack(context.architecture)
        if stack is not None:
            context.logger.info(
                "Environment generator: templating .env.example for detected "
                f"Python stack (framework={stack.web_framework or 'none'}, "
                f"database={stack.has_database}) - no LLM call needed."
            )
            context.generated_files.extend(generate_environment_files(stack))
            return

        context.logger.info("Executing environment generator step...")
        files = load_prompt_and_generate(context, "environment", "environment")
        context.generated_files.extend(files)
