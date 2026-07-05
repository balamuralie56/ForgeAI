"""
Durable Workspace Writer with transaction-like file rollbacks and manifest compiler for Documentation Plugin.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from forge_core.event_bus.models import Event
from forge_core.event_bus.service import EventBusService
from forge_core.model_router.service import ModelRouterService
from ..models import GeneratedDocFile
from ..exceptions import DocWriteError

logger = logging.getLogger("ForgeAI.Plugins.Documentation.Writers")


class DocWorkspaceWriter:
    """
    Handles atomic file writes for documentation folders with backups, rollbacks, and manifests.
    """

    def __init__(self, event_bus: EventBusService) -> None:
        """
        Initializes the document workspace writer.

        Args:
            event_bus (EventBusService): The system event bus.
        """
        self.event_bus = event_bus

    def write_docs(
        self,
        workspace: str,
        doc_files: List[GeneratedDocFile],
        project_id: str,
        model_router: Optional[ModelRouterService] = None,
    ) -> None:
        """
        Writes all compiled documentation files to the target workspace.
        Backs up existing files to support full transaction rollback on failure.

        Args:
            workspace (str): Destination workspace root path.
            doc_files (List[GeneratedDocFile]): Generated files list.
            project_id (str): The project ID.
            model_router (Optional[ModelRouterService]): Optional model router for merging.

        Raises:
            DocWriteError: If writing any file fails.
        """
        logger.info(
            f"Writing {len(doc_files)} generated documentation files to workspace: {workspace}"
        )
        workspace_dir = Path(workspace)

        written_files: List[Path] = []
        original_contents: Dict[Path, Optional[str]] = {}

        try:
            for df in doc_files:
                file_path = workspace_dir / df.path

                # Ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Read existing contents for rollback backup
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

                # Determine file content to write (merge or override)
                write_content = df.content
                if (
                    existing_content
                    and file_path.suffix in (".md", ".txt")
                    and model_router
                ):
                    try:
                        logger.info(
                            f"Merging generated documentation with existing file: {df.path}"
                        )
                        write_content = self._merge_doc_files(
                            existing_content, df.content, model_router
                        )
                    except Exception as merge_err:
                        logger.warning(
                            f"Failed to merge doc for '{df.path}', falling back to override: {merge_err}"
                        )
                        write_content = df.content

                # Write content to disk
                file_path.write_text(write_content, encoding="utf-8")
                written_files.append(file_path)

        except Exception as e:
            logger.error(
                f"Error during documentation workspace write: {e}. Initiating rollback..."
            )
            self._rollback(written_files, original_contents)
            raise DocWriteError(
                f"Failed to commit documentation to workspace: {e}"
            ) from e

        # Write manifest outside the transaction — failure here is non-fatal
        try:
            self._write_manifest(workspace_dir, doc_files, project_id)
        except Exception as manifest_err:
            logger.error(
                f"Failed to write docs_manifest.json (non-fatal): {manifest_err}"
            )

        logger.info("All documentation files successfully written to the workspace.")

    def _merge_doc_files(
        self,
        existing_code: str,
        new_code: str,
        model_router: ModelRouterService,
    ) -> str:
        """
        Uses model router to merge newly generated documentation with existing documentation.
        """
        try:
            prompt = (
                "You are a technical editor assistant. Merge the following new documentation content with "
                "the existing documentation. Retain all distinct sections, examples, or tables from both. "
                "Produce a single consolidated document.\n\n"
                f"=== Existing Documentation ===\n{existing_code}\n\n"
                f"=== New Documentation ===\n{new_code}\n"
            )
            response = model_router.generate(prompt)
            return response.text.strip()
        except Exception as e:
            logger.warning(f"Error merging doc files: {e}. Overwriting instead.")
            return new_code

    def _rollback(
        self,
        written_files: List[Path],
        original_contents: Dict[Path, Optional[str]],
    ) -> None:
        """
        Reverts all changes made during the write operation.
        """
        logger.info("Rolling back documentation workspace changes...")
        for path in written_files:
            try:
                if path.exists():
                    path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete file '{path}' during rollback: {e}")

        for path, original_content in original_contents.items():
            if original_content is not None:
                try:
                    path.write_text(original_content, encoding="utf-8")
                    logger.info(f"Restored original content for '{path}' from backup.")
                except Exception as e:
                    logger.error(
                        f"Failed to restore original backup content for '{path}': {e}"
                    )

        # Publish validation/write failed event
        self.event_bus.publish(
            Event(
                event_type="documentation.write_failed",
                data={"error": "Workspace write transaction rolled back"},
            )
        )
        logger.info("Documentation rollback complete.")

    def _write_manifest(
        self, workspace_dir: Path, doc_files: List[GeneratedDocFile], project_id: str
    ) -> None:
        """
        Generates and writes docs_manifest.json to the workspace root.
        """
        manifest_path = workspace_dir / "docs_manifest.json"

        # Build registry entry list
        manifest_entries = []
        for df in doc_files:
            file_path = workspace_dir / df.path
            size = len(df.content.encode("utf-8")) if file_path.exists() else 0
            manifest_entries.append(
                {
                    "path": df.path,
                    "category": df.category,
                    "size_bytes": size,
                }
            )

        stats = {
            "project_id": project_id,
            "generated_documents": len(doc_files),
            "output_directory": "docs",
            "manifest": manifest_entries,
        }

        try:
            manifest_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
            logger.info(f"docs_manifest.json successfully written to {manifest_path}")
        except Exception as e:
            logger.error(f"Failed to write docs_manifest.json: {e}")
