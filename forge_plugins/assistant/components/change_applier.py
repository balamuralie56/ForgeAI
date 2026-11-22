"""
Writes an approved change set to the project, and undoes it.

A change is only written if every file is still exactly as it was when the
change was proposed, and only undone if every file is still exactly as the
change left it - so neither ever overwrites edits the user made in between.
If a write fails part-way, the files already written are restored.
"""

import logging
from typing import List, Optional, Tuple

from ..exceptions import ChangeConflictError
from ..models import ChangeSet
from .workspace import ProjectWorkspace

logger = logging.getLogger("ForgeAI.Plugins.Assistant.ChangeApplier")


class ChangeApplier:
    """Applies and reverts change sets on disk."""

    def apply(self, workspace: ProjectWorkspace, change_set: ChangeSet) -> None:
        """
        Writes a change set's new file contents.

        Args:
            workspace (ProjectWorkspace): The project.
            change_set (ChangeSet): The change to write.

        Raises:
            ChangeConflictError: If a file changed since the proposal.
            OSError: If writing fails (already-written files are restored).
        """
        for change in change_set.files:
            current = workspace.read_text(change.path)
            if current != change.original:
                raise ChangeConflictError(
                    f"{change.path} changed after this edit was proposed. "
                    "Ask again so the edit is based on the current file."
                )
        self._write_all(
            workspace,
            [(c.path, c.original, c.updated) for c in change_set.files],
        )
        logger.info(
            f"Applied change set {change_set.id} to {len(change_set.files)} file(s)."
        )

    def revert(self, workspace: ProjectWorkspace, change_set: ChangeSet) -> None:
        """
        Restores the files a change set modified (deleting files it created).

        Args:
            workspace (ProjectWorkspace): The project.
            change_set (ChangeSet): An applied change.

        Raises:
            ChangeConflictError: If a file changed after the change was applied.
            OSError: If writing fails (already-restored files are re-applied).
        """
        for change in change_set.files:
            current = workspace.read_text(change.path)
            if current != change.updated:
                raise ChangeConflictError(
                    f"{change.path} was edited after this change was applied, so it "
                    "can't be undone automatically."
                )
        self._write_all(
            workspace,
            [(c.path, c.updated, c.original) for c in change_set.files],
        )
        logger.info(f"Reverted change set {change_set.id}.")

    @staticmethod
    def _write_all(
        workspace: ProjectWorkspace,
        writes: List[Tuple[str, Optional[str], Optional[str]]],
    ) -> None:
        """
        Performs (path, before, after) writes; `after=None` deletes the file.
        Restores `before` for every completed write if a later one fails.
        """
        done: List[Tuple[str, Optional[str]]] = []
        try:
            for path, before, after in writes:
                if after is None:
                    workspace.delete(path)
                else:
                    workspace.write_text(path, after)
                done.append((path, before))
        except OSError:
            logger.error(
                "Write failed; restoring files already written.", exc_info=True
            )
            for path, before in reversed(done):
                try:
                    if before is None:
                        workspace.delete(path)
                    else:
                        workspace.write_text(path, before)
                except OSError as restore_error:
                    logger.error(f"Could not restore {path}: {restore_error}")
            raise
