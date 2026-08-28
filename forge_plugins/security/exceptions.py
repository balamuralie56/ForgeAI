"""
Exceptions for the ForgeAI Security Plugin.
"""


class SecurityError(Exception):
    """Base exception class for all Security Plugin errors."""


class SecurityValidationError(SecurityError):
    """Raised when pre-flight security validation checks fail."""


class SecurityAnalysisError(SecurityError):
    """Raised when security scanners or code analysis fails."""


class SecurityWriteError(SecurityError):
    """Raised when writing security reports to the workspace fails."""
