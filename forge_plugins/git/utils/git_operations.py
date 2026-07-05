"""
Git operations adapter — thin subprocess wrapper for all local Git commands.
"""

import logging
import subprocess
from typing import List, Optional

from ..exceptions import GitOperationError

logger = logging.getLogger("ForgeAI.Plugins.Git.Utils")

_GIT_TIMEOUT_SECONDS = 30


def _run(args: List[str], cwd: str) -> str:
    """
    Executes a git subprocess command and returns stdout.

    Args:
        args (List[str]): Full argument list including 'git' as the first element.
        cwd (str): Working directory for the command.

    Returns:
        str: Captured stdout from the git process.

    Raises:
        GitOperationError: If the command exits with a non-zero code or times out.
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitOperationError(
            f"Git command timed out after {_GIT_TIMEOUT_SECONDS}s: {' '.join(args)}"
        ) from exc
    except FileNotFoundError as exc:
        raise GitOperationError(
            "git binary not found on PATH. Please install Git."
        ) from exc

    if result.returncode != 0:
        raise GitOperationError(
            f"Git command failed (exit {result.returncode}): {' '.join(args)}\n"
            f"stderr: {result.stderr.strip()}"
        )

    return result.stdout.strip()


class GitOperations:
    """
    Provides atomic, error-safe wrappers around git subprocess commands.
    All methods raise GitOperationError on failure.
    """

    def __init__(self, workspace: str) -> None:
        """
        Initializes the operations adapter.

        Args:
            workspace (str): Absolute path to the project workspace / git repository root.
        """
        self.workspace = workspace

    def init(self) -> None:
        """Initializes an empty git repository in the workspace."""
        _run(["git", "init"], self.workspace)
        logger.info(f"Initialised git repository at: {self.workspace}")

    def config_user(self, name: str = "ForgeAI", email: str = "forgeai@local") -> None:
        """Sets local git user identity for commits."""
        _run(["git", "config", "user.name", name], self.workspace)
        _run(["git", "config", "user.email", email], self.workspace)
        logger.info(f"Configured git identity: {name} <{email}>")

    def checkout(self, branch: str, create: bool = False) -> None:
        """
        Checks out a branch, optionally creating it.

        Args:
            branch (str): Target branch name.
            create (bool): If True, creates the branch before checking out.
        """
        args = ["git", "checkout", "-b", branch] if create else ["git", "checkout", branch]
        _run(args, self.workspace)
        logger.info(f"{'Created and checked out' if create else 'Checked out'} branch: {branch}")

    def add(self, paths: Optional[List[str]] = None) -> None:
        """
        Stages files for commit.

        Args:
            paths (Optional[List[str]]): Specific paths to stage. Stages all if None.
        """
        if paths:
            for path in paths:
                _run(["git", "add", path], self.workspace)
        else:
            _run(["git", "add", "."], self.workspace)
        logger.info(f"Staged {'specific paths' if paths else 'all changes'} for commit.")

    def commit(self, message: str) -> str:
        """
        Commits staged changes.

        Args:
            message (str): The commit message.

        Returns:
            str: The short SHA of the new commit.
        """
        _run(["git", "commit", "-m", message, "--allow-empty"], self.workspace)
        sha = self.rev_parse("HEAD")
        logger.info(f"Created commit '{sha}': {message[:60]}")
        return sha

    def tag(self, name: str, annotation: str = "") -> None:
        """
        Creates an annotated or lightweight tag.

        Args:
            name (str): The tag name (e.g. 'v1.2.0').
            annotation (str): If provided, creates an annotated tag with this message.
        """
        if annotation:
            _run(["git", "tag", "-a", name, "-m", annotation], self.workspace)
        else:
            _run(["git", "tag", name], self.workspace)
        logger.info(f"Created tag: {name}")

    def log(self, since_tag: Optional[str] = None, max_count: int = 50) -> str:
        """
        Retrieves the commit log.

        Args:
            since_tag (Optional[str]): If provided, returns commits since this tag.
            max_count (int): Maximum number of commits to retrieve.

        Returns:
            str: One-line formatted commit log.
        """
        args = ["git", "log", f"--max-count={max_count}", "--oneline"]
        if since_tag:
            args.append(f"{since_tag}..HEAD")
        return _run(args, self.workspace)

    def status(self) -> str:
        """Returns the short-format git status."""
        return _run(["git", "status", "--short"], self.workspace)

    def diff(self, staged: bool = False) -> str:
        """Returns the diff of unstaged (or staged) changes."""
        args = ["git", "diff"]
        if staged:
            args.append("--staged")
        return _run(args, self.workspace)

    def rev_parse(self, ref: str = "HEAD") -> str:
        """
        Resolves a git ref to its short SHA.

        Args:
            ref (str): Git ref to resolve (default HEAD).

        Returns:
            str: Short 8-character commit SHA.
        """
        return _run(["git", "rev-parse", "--short", ref], self.workspace)

    def describe(self) -> str:
        """
        Returns the most recent tag description.
        Returns '0.0.0' if no tags are found.
        """
        try:
            return _run(["git", "describe", "--tags", "--abbrev=0"], self.workspace)
        except GitOperationError:
            return "0.0.0"

    def is_git_repo(self) -> bool:
        """Returns True if the workspace is already a valid git repository."""
        try:
            _run(["git", "rev-parse", "--is-inside-work-tree"], self.workspace)
            return True
        except GitOperationError:
            return False
