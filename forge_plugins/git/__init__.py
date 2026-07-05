"""
ForgeAI Git Plugin package.
Exposes core services, exceptions, and models.
"""

from .service import GitService, ForgeAIGit
from .models import GitReport, GitCommit, GitTag, SemverBump, GitHubPR
from .exceptions import GitError, GitValidationError, GitOperationError, GitHubError
from .plugin import GitPlugin

__all__ = [
    "GitPlugin",
    "GitService",
    "ForgeAIGit",
    "GitReport",
    "GitCommit",
    "GitTag",
    "SemverBump",
    "GitHubPR",
    "GitError",
    "GitValidationError",
    "GitOperationError",
    "GitHubError",
]
