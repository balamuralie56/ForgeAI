"""
CommitStep — stages all generated project files and creates a semantic commit.
Commit messages are generated deterministically from the file list.
LLM-enhanced messages are used if 'llm_commit_messages: true' is set in config.
"""

import logging
from datetime import datetime, timezone
from typing import List

from ..utils.git_pipeline import GitContext, GitPipelineStep
from ..models import GitCommit

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")


def _build_deterministic_message(project_id: str, file_count: int) -> str:
    """
    Builds a deterministic semantic commit message.

    Args:
        project_id (str): The project identifier.
        file_count (int): Total number of staged files.

    Returns:
        str: A formatted conventional commit message.
    """
    return f"forge(generator): add {file_count} generated files for {project_id}"


def _collect_all_file_paths(context: GitContext) -> List[str]:
    """
    Collects relative file paths from implementation, test, and documentation reports.

    Args:
        context (GitContext): The shared pipeline context.

    Returns:
        List[str]: Deduplicated list of all generated file paths.
    """
    paths: List[str] = []

    for gf in context.implementation_report.files:
        paths.append(gf.path)

    for tf in context.test_report.test_files:
        paths.append(tf.path)

    for df in context.doc_report.doc_files:
        paths.append(df.path)

    # Deduplicate preserving order
    seen = set()
    unique_paths: List[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    return unique_paths


class CommitStep(GitPipelineStep):
    """
    Stages all generated files and creates a commit with a semantic message.
    """

    @property
    def name(self) -> str:
        return "Commit Step"

    def run(self, context: GitContext) -> None:
        """
        Collects file paths from all upstream reports, stages them, generates a commit
        message, commits, and appends the resulting GitCommit to the context.

        Args:
            context (GitContext): The shared pipeline context.
        """
        file_paths = _collect_all_file_paths(context)
        context.logger.info(
            f"Staging {len(file_paths)} generated files for commit in project '{context.spec.project_id}'."
        )

        # Stage all files
        context.git_ops.add()

        # Determine commit message strategy
        git_config = getattr(context.configuration, "git", None)
        use_llm = getattr(git_config, "llm_commit_messages", False) if git_config else False

        if use_llm:
            message = self._generate_llm_message(context, file_paths)
        else:
            message = _build_deterministic_message(context.spec.project_id, len(file_paths))

        context.logger.info(f"Committing with message: {message}")
        sha = context.git_ops.commit(message)

        commit = GitCommit(
            sha=sha,
            message=message,
            files=file_paths,
            author="ForgeAI",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        context.commits.append(commit)
        context.logger.info(f"Commit created: {sha}")

    def _generate_llm_message(self, context: GitContext, file_paths: List[str]) -> str:
        """
        Uses the model router to generate an enriched conventional commit message.
        Falls back to deterministic message on any failure.

        Args:
            context (GitContext): The shared pipeline context.
            file_paths (List[str]): List of staged file paths.

        Returns:
            str: The generated commit message.
        """
        try:
            prompt = (
                "You are a senior software engineer. Generate a single conventional commit message "
                f"for committing {len(file_paths)} AI-generated files for the '{context.spec.project_id}' project.\n"
                "The message must follow the conventional commit format: type(scope): description\n"
                f"Types of files include: source code, tests, and documentation.\n"
                f"Example files: {', '.join(file_paths[:5])}\n"
                "Return ONLY the commit message string — no explanations, no quotes, no extra text."
            )
            response = context.model_router.generate(prompt)
            message = response.text.strip().split("\n")[0].strip()
            if message:
                return message
        except Exception as exc:
            context.logger.warning(
                f"LLM commit message generation failed, using deterministic fallback: {exc}"
            )

        return _build_deterministic_message(context.spec.project_id, len(file_paths))
