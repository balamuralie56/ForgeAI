"""
Service interface and concrete implementation for the ForgeAI History Engine.
Keeps a durable, per-run record of workflows and the reports each one produced.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from forge_core.kernel.lifecycle import LifecycleComponent

from .exceptions import InvalidSnapshotError
from .models import REPORT_KINDS, RunDetail, RunSummary, StorageUsage
from .store import SQLiteHistoryStore

logger = logging.getLogger("ForgeAI.History.Service")


class HistoryService(ABC):
    """
    Service registry interface for the History Engine.
    """

    @abstractmethod
    def record_run_snapshot(self, snapshot: Dict[str, Any], model: str) -> None:
        """
        Records (or updates) a workflow run from its serialized state.

        Args:
            snapshot (Dict[str, Any]): A workflow's `to_dict()` representation.
            model (str): The LLM model configured when the snapshot was taken.

        Raises:
            InvalidSnapshotError: If the snapshot lacks a workflow ID.
            HistoryError: If persistence fails.
        """

    @abstractmethod
    def list_runs(self, limit: int = 50, offset: int = 0) -> List[RunSummary]:
        """Returns recorded runs, newest first."""

    @abstractmethod
    def count_runs(self) -> int:
        """Returns the total number of recorded runs."""

    @abstractmethod
    def get_run(self, workflow_id: str) -> Optional[RunDetail]:
        """Returns one run's detail, or None if it is not recorded."""

    @abstractmethod
    def get_artifact(self, workflow_id: str, kind: str) -> Optional[Dict[str, Any]]:
        """Returns one stored report of a run, or None if it does not exist."""

    @abstractmethod
    def delete_run(self, workflow_id: str) -> bool:
        """
        Deletes a run and its stored reports.

        Returns:
            bool: True if the run existed and was deleted.
        """

    @abstractmethod
    def storage_usage(self) -> StorageUsage:
        """Returns the storage the history database consumes."""


class ForgeAIHistoryService(HistoryService, LifecycleComponent):
    """
    Concrete History Service backed by a dedicated SQLite database.
    """

    def __init__(self, db_path: str = "forge_data/databases/forge_history.db") -> None:
        """
        Args:
            db_path (str): Filepath of the history database.
        """
        self._store = SQLiteHistoryStore(db_path)

    def initialize(self) -> None:
        """Opens the history database (lifecycle hook)."""
        self._store.initialize()

    def shutdown(self) -> None:
        """Closes the history database (lifecycle hook)."""
        self._store.close()

    def record_run_snapshot(self, snapshot: Dict[str, Any], model: str) -> None:
        workflow_id = snapshot.get("id") if isinstance(snapshot, dict) else None
        if not isinstance(workflow_id, str) or not workflow_id:
            raise InvalidSnapshotError("Workflow snapshot has no 'id'.")

        context = snapshot.get("context")
        context = context if isinstance(context, dict) else {}
        goal = context.get("goal")

        now = time.time()
        run = RunSummary(
            workflow_id=workflow_id,
            name=str(snapshot.get("name", "")),
            goal=goal if isinstance(goal, str) else "",
            workflow_type=str(snapshot.get("type", "")),
            state=str(snapshot.get("state", "")),
            progress=float(snapshot.get("progress", 0.0)),
            model=model,
            created_at=float(snapshot.get("created_at", now)),
            updated_at=float(snapshot.get("updated_at", now)),
        )
        artifacts = {
            kind: json.dumps(context[kind])
            for kind in sorted(REPORT_KINDS)
            if isinstance(context.get(kind), dict)
        }
        self._store.save_run(
            run,
            stages=list(snapshot.get("stages") or []),
            errors=dict(snapshot.get("errors") or {}),
            artifacts=artifacts,
        )

    def list_runs(self, limit: int = 50, offset: int = 0) -> List[RunSummary]:
        return self._store.list_runs(max(1, limit), max(0, offset))

    def count_runs(self) -> int:
        return self._store.count_runs()

    def get_run(self, workflow_id: str) -> Optional[RunDetail]:
        record = self._store.get_run(workflow_id)
        if record is None:
            return None
        return RunDetail(
            summary=record["summary"],
            stages=record["stages"],
            errors=record["errors"],
            artifact_kinds=record["artifact_kinds"],
        )

    def get_artifact(self, workflow_id: str, kind: str) -> Optional[Dict[str, Any]]:
        body = self._store.get_artifact(workflow_id, kind)
        if body is None:
            return None
        data: Dict[str, Any] = json.loads(body)
        return data

    def delete_run(self, workflow_id: str) -> bool:
        deleted = self._store.delete_run(workflow_id)
        if deleted:
            logger.info(f"Deleted run '{workflow_id}' from history.")
        return deleted

    def storage_usage(self) -> StorageUsage:
        return StorageUsage(
            database_bytes=self._store.database_bytes(),
            run_count=self._store.count_runs(),
            artifact_bytes_by_run=self._store.artifact_bytes_by_run(),
        )
