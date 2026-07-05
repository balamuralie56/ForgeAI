"""
BranchStep — creates and checks out the project delivery branch.
"""

import logging

from ..utils.git_pipeline import GitContext, GitPipelineStep
from ..exceptions import GitOperationError

logger = logging.getLogger("ForgeAI.Plugins.Git.Components")


class BranchStep(GitPipelineStep):
    """
    Creates and checks out a delivery branch named '{prefix}/{project_id}'.
    Falls back to an existing branch if creation fails due to a duplicate.
    """

    @property
    def name(self) -> str:
        return "Branch Step"

    def run(self, context: GitContext) -> None:
        """
        Determines the branch name from configuration and project spec,
        then creates and checks out that branch.

        Args:
            context (GitContext): The shared pipeline context.
        """
        git_config = getattr(context.configuration, "git", None)
        prefix = getattr(git_config, "branch_prefix", "forge") if git_config else "forge"

        branch_name = f"{prefix}/{context.spec.project_id}"
        context.logger.info(f"Preparing delivery branch: {branch_name}")

        # Ensure there is at least one commit so branching is valid
        if not context.git_ops.is_git_repo():
            context.git_ops.init()
            context.git_ops.config_user()

        try:
            context.git_ops.checkout(branch_name, create=True)
            context.logger.info(f"Created and checked out branch: {branch_name}")
        except GitOperationError:
            # Branch may already exist — attempt simple checkout
            context.logger.warning(
                f"Branch '{branch_name}' may already exist. Attempting checkout without create flag."
            )
            context.git_ops.checkout(branch_name, create=False)

        context.branch = branch_name
