"""
Code Validation step for the Developer Plugin.
"""

from typing import Optional

from forge_plugins.developer.utils.pipeline import ImplementationContext, PipelineStep
from forge_plugins.developer.validators.code_validator import GeneratedCodeValidator

# Issues logged individually before the rest are summarized as a count.
_MAX_LOGGED_ISSUES = 20


class CodeValidationStep(PipelineStep):
    """
    Statically validates every file generated so far and records the result on
    the context, so the report and status reflect whether the code can run.
    """

    def __init__(self, validator: Optional[GeneratedCodeValidator] = None) -> None:
        """
        Args:
            validator (Optional[GeneratedCodeValidator]): Validator to use;
                defaults to a GeneratedCodeValidator.
        """
        self._validator = validator or GeneratedCodeValidator()

    @property
    def name(self) -> str:
        return "Code Validator"

    def run(self, context: ImplementationContext) -> None:
        """
        Validates `context.generated_files` and stores the result in `context.validation`.

        Args:
            context (ImplementationContext): Shared pipeline context.
        """
        result = self._validator.validate(context.generated_files)
        context.validation = result

        context.logger.info(
            f"Code validation: {result.status.value} - {result.checked_files} files checked, "
            f"{len(result.errors)} errors, {len(result.warnings)} warnings."
        )
        for issue in result.issues[:_MAX_LOGGED_ISSUES]:
            location = f"{issue.path}:{issue.line}" if issue.line else issue.path
            context.logger.warning(
                f"[{issue.severity.value}] {issue.check} {location}: {issue.message}"
            )
        if len(result.issues) > _MAX_LOGGED_ISSUES:
            context.logger.warning(
                f"...and {len(result.issues) - _MAX_LOGGED_ISSUES} more validation issues."
            )
