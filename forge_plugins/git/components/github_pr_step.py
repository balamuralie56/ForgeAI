"""
GitHubPRStep — creates a Pull Request on GitHub using PyGithub.
This step is entirely optional and config-gated.
If github_enabled is False, or PyGithub is not installed, the step is skipped silently.
"""

import logging

from forge_core.event_bus.models import Event

from ..utils.git_pipeline import GitContext, GitPipelineStep
from ..models import GitHubPR
from ..exceptions import GitHubError

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")


class GitHubPRStep(GitPipelineStep):
    """
    Creates a GitHub Pull Request from the project delivery branch to the default base branch.
    Completely skipped when GitHub integration is disabled or PyGithub is unavailable.
    """

    @property
    def name(self) -> str:
        return "GitHub PR Step"

    def run(self, context: GitContext) -> None:
        """
        Checks GitHub configuration, generates a PR title and body using LLM,
        then creates the PR. Any GitHub API failure is logged and swallowed (non-fatal).

        Args:
            context (GitContext): The shared pipeline context.
        """
        git_config = getattr(context.configuration, "git", None)
        github_enabled = getattr(git_config, "github_enabled", False) if git_config else False

        if not github_enabled:
            context.logger.info("GitHub integration disabled — skipping PR creation.")
            context.event_bus.publish(
                Event(
                    event_type="git.github_skipped",
                    data={
                        "project_id": context.spec.project_id,
                        "reason": "github_enabled is False",
                    },
                )
            )
            return

        try:
            from github import Github, GithubException  # type: ignore[import-not-found]
        except ImportError:
            context.logger.warning(
                "PyGithub is not installed. GitHub PR creation skipped. "
                "Run: pip install PyGithub"
            )
            context.event_bus.publish(
                Event(
                    event_type="git.github_skipped",
                    data={
                        "project_id": context.spec.project_id,
                        "reason": "PyGithub not installed",
                    },
                )
            )
            return

        token = getattr(git_config, "github_token", "")
        owner = getattr(git_config, "github_owner", "")
        repo_name = getattr(git_config, "github_repo", "")
        base_branch = getattr(git_config, "default_branch", "main")
        branch = context.branch or f"forge/{context.spec.project_id}"

        pr_title, pr_body = self._generate_pr_content(context)

        try:
            gh = Github(token)
            repo = gh.get_repo(f"{owner}/{repo_name}")
            pr = repo.create_pull(
                title=pr_title,
                body=pr_body,
                head=branch,
                base=base_branch,
            )
            context.pr = GitHubPR(
                url=pr.html_url,
                number=pr.number,
                title=pr.title,
                branch=branch,
                base=base_branch,
            )
            context.logger.info(
                f"GitHub PR created: #{pr.number} — {pr.html_url}"
            )
        except Exception as exc:
            # GitHub errors are non-fatal — log and continue
            context.logger.error(
                f"GitHub PR creation failed (non-fatal): {exc}"
            )
            context.event_bus.publish(
                Event(
                    event_type="git.operation_failed",
                    data={
                        "project_id": context.spec.project_id,
                        "step": self.name,
                        "error": str(exc),
                    },
                )
            )

    def _generate_pr_content(self, context: GitContext) -> tuple:
        """
        Generates the PR title and body using the LLM.
        Falls back to deterministic defaults on any failure.

        Args:
            context (GitContext): The shared pipeline context.

        Returns:
            tuple: (title: str, body: str)
        """
        from pathlib import Path

        prompt_path = Path(__file__).parent.parent / "prompts" / "pr_description.txt"
        if not prompt_path.exists():
            return self._deterministic_pr_content(context)

        commit_summaries = "\n".join(
            f"- {c.sha}: {c.message}" for c in context.commits
        )
        version = context.semver.recommended if context.semver else "0.1.0"

        try:
            template = prompt_path.read_text(encoding="utf-8")
            prompt = template.format(
                project_id=context.spec.project_id,
                version=version,
                commits=commit_summaries or "(no commits recorded)",
                branch=context.branch,
            )
            response = context.model_router.generate(prompt)
            text = response.text.strip()
            # Expect LLM to return: first line = title, rest = body
            lines = text.split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            if title:
                return title, body
        except Exception as exc:
            context.logger.warning(
                f"LLM PR content generation failed, using deterministic fallback: {exc}"
            )

        return self._deterministic_pr_content(context)

    def _deterministic_pr_content(self, context: GitContext) -> tuple:
        """Builds a deterministic PR title and body."""
        version = context.semver.recommended if context.semver else "0.1.0"
        title = f"forge({context.spec.project_id}): autonomous delivery v{version}"
        body = (
            f"## Autonomous ForgeAI Delivery\n\n"
            f"**Project**: `{context.spec.project_id}`\n"
            f"**Version**: `v{version}`\n"
            f"**Branch**: `{context.branch}`\n\n"
            f"### Commits\n"
            + "\n".join(f"- `{c.sha}` {c.message}" for c in context.commits)
        )
        return title, body
