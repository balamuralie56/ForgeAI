"""
Durable Workspace Writer with failure rollback and test merge support for the Tester Plugin.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from forge_core.event_bus.models import Event
from forge_core.event_bus.service import EventBusService
from forge_core.model_router.service import ModelRouterService
from forge_plugins.tester.exceptions import TesterWriteError
from forge_plugins.tester.models import GeneratedTestFile

logger = logging.getLogger("ForgeAI.Plugins.Tester.Writers")


class TestWorkspaceWriter:
    """Handles atomic, transaction-like file writes for test suites with merging and rollback."""

    __test__ = False

    def __init__(self, event_bus: EventBusService) -> None:
        """
        Initializes the test workspace writer.

        Args:
            event_bus (EventBusService): Core system event bus.
        """
        self.event_bus = event_bus

    def write_files(
        self,
        workspace_path: str,
        files: List[GeneratedTestFile],
        project_id: str,
        model_router: Optional[ModelRouterService] = None,
    ) -> None:
        """
        Writes all generated test files to the target workspace under 'tests/'.
        If a file already exists and is a python test file, merges new tests with existing ones.
        If any write fails, rolls back all changes to restore original workspace state.

        Args:
            workspace_path (str): Target directory path.
            files (List[GeneratedTestFile]): List of GeneratedTestFile objects.
            project_id (str): Associated project ID.
            model_router (Optional[ModelRouterService]): Model router to perform code merging.

        Raises:
            TesterWriteError: If writing or rollbacks fail.
        """
        logger.info(
            f"Writing {len(files)} generated test files to workspace: {workspace_path}"
        )

        base_dir = Path(workspace_path).resolve()
        written_files: List[Path] = []
        original_contents: Dict[Path, Optional[str]] = {}

        try:
            for tf in files:
                # Ensure the path is resolved and is within the workspace directory
                file_path = (base_dir / tf.path).resolve()
                if not str(file_path).startswith(str(base_dir)):
                    raise TesterWriteError(
                        f"Security violation: File path '{tf.path}' escapes the workspace directory."
                    )

                # Store original state for rollback
                existing_content: Optional[str] = None
                if file_path.exists():
                    try:
                        existing_content = file_path.read_text(encoding="utf-8")
                        original_contents[file_path] = existing_content
                    except Exception as e:
                        logger.warning(
                            f"Could not read existing file '{file_path}' for rollback backup: {e}"
                        )
                        original_contents[file_path] = None
                else:
                    original_contents[file_path] = None

                # Perform merge if file exists, is a python file, and model router is provided
                write_content = tf.content
                if existing_content and file_path.suffix == ".py" and model_router:
                    try:
                        logger.info(
                            f"Merging generated tests with existing file: {tf.path}"
                        )
                        write_content = self._merge_test_files(
                            existing_content, tf.content, model_router
                        )
                    except Exception as merge_err:
                        logger.warning(
                            f"Failed to merge tests for '{tf.path}', falling back to overwrite: {merge_err}"
                        )
                        write_content = tf.content

                # Ensure parent directories exist
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write content
                file_path.write_text(write_content, encoding="utf-8")
                written_files.append(file_path)

                # Emit tester.file_written event
                self.event_bus.publish(
                    Event(
                        event_type="tester.file_written",
                        data={
                            "project_id": project_id,
                            "path": tf.path,
                            "absolute_path": str(file_path),
                        },
                    )
                )

            logger.info("All test files successfully written to the workspace.")

        except Exception as e:
            logger.error(
                f"Error during test workspace write: {e}. Initiating rollback..."
            )
            self._rollback(written_files, original_contents)
            raise TesterWriteError(f"Test workspace atomic write failed: {e}") from e

    def write_manifest(self, workspace_path: str, stats: Dict[str, Any]) -> None:
        """
        Writes test_manifest.json to the workspace root.

        Args:
            workspace_path (str): Target directory path.
            stats (Dict[str, Any]): Test run details and stats.
        """
        base_dir = Path(workspace_path).resolve()
        manifest_path = base_dir / "test_manifest.json"
        try:
            manifest_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
            logger.info(f"test_manifest.json successfully written to {manifest_path}")
        except Exception as e:
            logger.error(f"Failed to write test_manifest.json: {e}")

    def _merge_test_files(
        self, existing_code: str, new_code: str, model_router: ModelRouterService
    ) -> str:
        """
        Uses model router to merge newly generated tests with existing tests.
        """
        try:
            current_dir = Path(__file__).parent.parent
            merge_prompt_path = current_dir / "prompts" / "merge.txt"

            if not merge_prompt_path.exists():
                logger.warning("Merge prompt template not found. Overwriting instead.")
                return new_code

            prompt_template = merge_prompt_path.read_text(encoding="utf-8")
            prompt = prompt_template.format(
                existing_code=existing_code, new_code=new_code
            )

            response = model_router.generate(prompt)
            merged_code = response.text.strip()

            # Clean markdown wraps from response
            if merged_code.startswith("```"):
                lines = merged_code.splitlines()
                if len(lines) >= 2:
                    # Remove first line if it starts with ```
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    # Remove last line if it is ```
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    merged_code = "\n".join(lines).strip()

            return merged_code
        except Exception as e:
            logger.warning(f"Error merging test files: {e}. Falling back to override.")
            return new_code

    def _rollback(
        self, written_files: List[Path], original_contents: Dict[Path, Optional[str]]
    ) -> None:
        """
        Rolls back written test files, deleting new files and restoring backups.
        """
        for file_path in written_files:
            try:
                backup = original_contents.get(file_path)
                if backup is None:
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug(
                            f"Rollback deleted newly created test file: {file_path}"
                        )
                else:
                    file_path.write_text(backup, encoding="utf-8")
                    logger.debug(f"Rollback restored original test file: {file_path}")

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
                    f"Critically failed to roll back test file '{file_path}': {rollback_err}",
                    exc_info=True,
                )
