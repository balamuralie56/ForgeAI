"""
ChangelogStep — generates and writes a structured CHANGELOG.md to the workspace.
"""

import logging
from pathlib import Path


from ..utils.git_pipeline import GitContext, GitPipelineStep

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")

_CHANGELOG_FILENAME = "CHANGELOG.md"


def _build_deterministic_changelog(context: GitContext) -> str:
    """
    Builds a minimal deterministic CHANGELOG.md from the commit and semver context.

    Args:
        context (GitContext): The shared pipeline context.

    Returns:
        str: Markdown-formatted changelog string.
    """
    version = context.semver.recommended if context.semver else "0.1.0"
    project_id = context.spec.project_id

    lines = [
        f"# Changelog — {project_id}",
        "",
        f"## [{version}] — Autonomous ForgeAI Release",
        "",
        "### Added",
    ]

    for commit in context.commits:
        lines.append(f"- {commit.message} (`{commit.sha}`)")

    if not context.commits:
        lines.append("- Autonomous generation of project files by ForgeAI pipeline.")

    lines += [
        "",
        "---",
        "*Changelog generated autonomously by ForgeAI.*",
    ]
    return "\n".join(lines)


class ChangelogStep(GitPipelineStep):
    """
    Generates a CHANGELOG.md using LLM enrichment (with deterministic fallback)
    and writes it to the workspace root.
    """

    @property
    def name(self) -> str:
        return "Changelog Step"

    def run(self, context: GitContext) -> None:
        """
        Generates the changelog content, writes it to the workspace, and stores
        the content in context.changelog.

        Args:
            context (GitContext): The shared pipeline context.
        """
        context.logger.info("Generating CHANGELOG.md...")

        changelog_content = self._generate_changelog(context)
        context.changelog = changelog_content

        changelog_path = Path(context.workspace) / _CHANGELOG_FILENAME
        try:
            changelog_path.write_text(changelog_content, encoding="utf-8")
            context.logger.info(f"CHANGELOG.md written to: {changelog_path}")
        except Exception as exc:
            context.logger.error(f"Failed to write CHANGELOG.md: {exc}")
            raise

    def _generate_changelog(self, context: GitContext) -> str:
        """
        Attempts LLM generation, falls back to deterministic changelog on failure.

        Args:
            context (GitContext): The shared pipeline context.

        Returns:
            str: Markdown changelog content.
        """
        prompt_path = Path(__file__).parent.parent / "prompts" / "changelog.txt"

        if not prompt_path.exists():
            context.logger.warning(
                "changelog.txt prompt missing — using deterministic changelog."
            )
            return _build_deterministic_changelog(context)

        commit_summaries = "\n".join(f"- {c.sha}: {c.message}" for c in context.commits)
        version = context.semver.recommended if context.semver else "0.1.0"

        try:
            template = prompt_path.read_text(encoding="utf-8")
            prompt = template.format(
                project_id=context.spec.project_id,
                version=version,
                commits=commit_summaries or "(no commits recorded)",
            )
            response = context.model_router.generate(prompt)
            content = response.text.strip()
            if content:
                return content
        except Exception as exc:
            context.logger.warning(
                f"LLM changelog generation failed, using deterministic fallback: {exc}"
            )

        return _build_deterministic_changelog(context)
