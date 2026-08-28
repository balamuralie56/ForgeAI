"""
Exceptions for the ForgeAI Reviewer Plugin.
"""


class ReviewerError(Exception):
    """Base exception class for all Reviewer Plugin errors."""


class ReviewerValidationError(ReviewerError):
    """Raised when pre-flight review validation checks fail."""


class ReviewerAnalysisError(ReviewerError):
    """Raised when code review scanners or analysis fails."""


class ReviewerWriteError(ReviewerError):
    """Raised when writing review reports to the workspace fails."""
