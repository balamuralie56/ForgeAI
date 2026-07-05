"""
Durable Workspace Writer with failure rollback for the Developer Plugin.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from forge_core.event_bus.models import Event
from forge_core.event_bus.service import EventBusService
from forge_plugins.developer.exceptions import DeveloperWriteError
from forge_plugins.developer.models import GeneratedFile

logger = logging.getLogger("ForgeAI.Plugins.Developer.Writers")


class WorkspaceWriter:
    """Handles atomic, transaction-like file writes to the workspace with clean rollbacks."""

    def __init__(self, event_bus: EventBusService) -> None:
        """
        Initializes the writer with the system event bus.

        Args:
            event_bus (EventBusService): Core system event bus.
        """
        self.event_bus = event_bus

    def write_files(
        self, workspace_path: str, files: List[GeneratedFile], project_id: str
    ) -> None:
        """
        Writes all generated files to the target workspace.
        If any write fails, rolls back all changes to restore original workspace state.

        Args:
            workspace_path (str): Target directory path.
            files (List[GeneratedFile]): List of GeneratedFile objects.
            project_id (str): Associated project ID.

        Raises:
            DeveloperWriteError: If writing or rollbacks fail.
        """
        logger.info(
            f"Writing {len(files)} generated files to workspace: {workspace_path}"
        )

        base_dir = Path(workspace_path).resolve()
        written_files: List[Path] = []
        original_contents: Dict[Path, Optional[str]] = {}

        try:
            for gf in files:
                # Ensure the path is resolved and is within the workspace directory
                file_path = (base_dir / gf.path).resolve()
                if not str(file_path).startswith(str(base_dir)):
                    raise DeveloperWriteError(
                        f"Security violation: File path '{gf.path}' escapes the workspace directory."
                    )

                # Store original state for rollback
                if file_path.exists():
                    try:
                        original_contents[file_path] = file_path.read_text(
                            encoding="utf-8"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Could not read existing file '{file_path}' for rollback backup: {e}"
                        )
                        original_contents[file_path] = None
                else:
                    original_contents[file_path] = None

                # Ensure parent directories exist
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write content
                file_path.write_text(gf.content, encoding="utf-8")
                written_files.append(file_path)

                # Emit file_written event
                self.event_bus.publish(
                    Event(
                        event_type="developer.file_written",
                        data={
                            "project_id": project_id,
                            "path": gf.path,
                            "absolute_path": str(file_path),
                        },
                    )
                )

            logger.info("All files successfully written to the workspace.")

        except Exception as e:
            logger.error(f"Error during workspace write: {e}. Initiating rollback...")
            self._rollback(written_files, original_contents)
            raise DeveloperWriteError(f"Workspace atomic write failed: {e}") from e

    def _rollback(
        self, written_files: List[Path], original_contents: Dict[Path, Optional[str]]
    ) -> None:
        """
        Rolls back written files, deleting new files and restoring backups.

        Args:
            written_files (List[Path]): Files written in this transaction.
            original_contents (Dict[Path, Optional[str]]): Original contents of files.
        """
        for file_path in written_files:
            try:
                backup = original_contents.get(file_path)
                if backup is None:
                    # File was newly created, so delete it
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug(
                            f"Rollback deleted newly created file: {file_path}"
                        )
                else:
                    # File existed, restore original content
                    file_path.write_text(backup, encoding="utf-8")
                    logger.debug(f"Rollback restored original file: {file_path}")

                # Clean up empty parent directories up to workspace root
                parent = file_path.parent
                while parent and parent != Path.cwd() and parent.exists():
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        logger.debug(f"Rollback removed empty directory: {parent}")
                        parent = parent.parent
                    else:
                        break
            except Exception as rollback_err:
                logger.error(
                    f"Critically failed to roll back file '{file_path}': {rollback_err}",
                    exc_info=True,
                )
