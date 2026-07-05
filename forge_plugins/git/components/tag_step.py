"""
TagStep — applies a semantic version tag to the current HEAD commit.
"""

import logging

from ..utils.git_pipeline import GitContext, GitPipelineStep
from ..models import GitTag

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")


class TagStep(GitPipelineStep):
    """
    Creates an annotated git tag based on the SemverBump recommendation from the pipeline context.
    Skips tagging gracefully if semver computation was not performed.
    """

    @property
    def name(self) -> str:
        return "Tag Step"

    def run(self, context: GitContext) -> None:
        """
        Reads the recommended version from context.semver and applies an annotated tag.

        Args:
            context (GitContext): The shared pipeline context.
        """
        if not context.semver:
            context.logger.warning(
                "SemverBump not present in context. Skipping tag creation."
            )
            return

        tag_name = f"v{context.semver.recommended}"
        annotation = (
            f"ForgeAI automated release {tag_name} for project '{context.spec.project_id}'. "
            f"Bump type: {context.semver.bump_type}. {context.semver.rationale}"
        )

        context.logger.info(f"Creating annotated tag: {tag_name}")
        context.git_ops.tag(tag_name, annotation)

        sha = context.git_ops.rev_parse("HEAD")
        git_tag = GitTag(name=tag_name, sha=sha, annotation=annotation)
        context.tags.append(git_tag)
        context.logger.info(f"Tag '{tag_name}' applied at commit {sha}.")
