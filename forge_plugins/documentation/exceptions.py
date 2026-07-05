"""
Exceptions for the ForgeAI Documentation Plugin.
"""


class DocumentationError(Exception):
    """Base exception class for all Documentation Plugin errors."""

    pass


class DocValidationError(DocumentationError):
    """Raised when specifications or workspace integrity checks fail."""

    pass


class DocInferenceError(DocumentationError):
    """Raised when model inference or JSON decoding fails during doc generation."""

    pass


class DocWriteError(DocumentationError):
    """Raised when writing documentation files or performing backup rollback fails."""

    pass
