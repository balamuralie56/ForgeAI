"""
Dependency Generator component for the Developer Plugin.
"""

from forge_plugins.developer.utils.pipeline import PipelineStep, ImplementationContext
from forge_plugins.developer.utils.prompt_helper import load_prompt_and_generate
from forge_plugins.developer.utils.stack_templates import (
    detect_python_stack,
    generate_dependency_files,
)


class DependencyGenerator(PipelineStep):
    """Generates package dependency definition files."""

    @property
    def name(self) -> str:
        return "Dependency Generator"

    def run(self, context: ImplementationContext) -> None:
        """
        Runs the dependency generator, extending generated files in-context.
        Skips the LLM call entirely for a confidently-detected Python stack -
        requirements.txt is boilerplate, not a judgment call. Falls back to
        LLM generation unchanged for anything else.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        stack = detect_python_stack(context.architecture)
        if stack is not None:
            context.logger.info(
                "Dependency generator: templating requirements.txt for detected "
                f"Python stack (framework={stack.web_framework or 'none'}, "
                f"database={stack.has_database}) - no LLM call needed."
            )
            context.generated_files.extend(generate_dependency_files(stack))
            return

        context.logger.info("Executing dependency generator step...")
        files = load_prompt_and_generate(context, "dependency", "dependency")
        context.generated_files.extend(files)
