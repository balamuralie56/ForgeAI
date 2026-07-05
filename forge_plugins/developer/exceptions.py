"""
Custom exceptions for the ForgeAI Developer Plugin.
"""


class DeveloperError(Exception):
    """Base exception for all developer plugin errors."""

    pass


class DeveloperInferenceError(DeveloperError):
    """Raised when the LLM generation or parsing fails."""

    pass


class DeveloperValidationError(DeveloperError):
    """Raised when validation of input specs or paths fails."""

    pass


class DeveloperWriteError(DeveloperError):
    """Raised when writing files to the workspace fails."""

    pass
