"""
Exceptions for the ForgeAI Tester Plugin.
"""


class TesterError(Exception):
    """Base exception class for all Tester Plugin errors."""

    __test__ = False


class TestingInferenceError(TesterError):
    """Raised when model inference or JSON decoding fails during testing."""

    pass


class TestValidationError(TesterError):
    """Raised when specification or report validation checks fail."""

    __test__ = False


class TesterWriteError(TesterError):
    """Raised when writing generated test files to workspace or rollback fails."""

    __test__ = False
