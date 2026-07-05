"""
Exceptions for the ForgeAI Git Plugin.
"""


class GitError(Exception):
    """Base exception class for all Git Plugin errors."""

    pass


class GitValidationError(GitError):
    """Raised when pre-flight validation checks fail (missing git binary, missing config, etc.)."""

    pass


class GitOperationError(GitError):
    """Raised when a git subprocess command returns a non-zero exit code or times out."""

    pass


class GitHubError(GitError):
    """Raised when a GitHub API call fails. Non-fatal — logged and skipped by default."""

    pass
