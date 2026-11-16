"""
SQLite persistence for the ForgeAI History Engine.

Kept separate from the Memory Engine's key-value store on purpose: history is
relational (runs own artifacts), needs to be listed and deleted per run, and
must not be overwritten by later runs the way singleton project-memory keys are.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import HistoryError
from .models import RunSummary

logger = logging.getLogger("ForgeAI.History.Store")

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE runs (
    workflow_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    goal          TEXT NOT NULL,
    workflow_type TEXT NOT NULL,
    state         TEXT NOT NULL,
    progress      REAL NOT NULL,
    model         TEXT NOT NULL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    stages_json   TEXT NOT NULL,
    errors_json   TEXT NOT NULL
);
CREATE INDEX idx_runs_created_at ON runs (created_at DESC);
CREATE TABLE artifacts (
    workflow_id  TEXT NOT NULL REFERENCES runs (workflow_id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    content_json TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    updated_at   REAL NOT NULL,
    PRIMARY KEY (workflow_id, kind)
);
"""

_RUN_COLUMNS = (
    "workflow_id, name, goal, workflow_type, state, progress, model, "
    "created_at, updated_at"
)


def _row_to_summary(row: sqlite3.Row) -> RunSummary:
    return RunSummary(
        workflow_id=row["workflow_id"],
        name=row["name"],
        goal=row["goal"],
        workflow_type=row["workflow_type"],
        state=row["state"],
        progress=row["progress"],
        model=row["model"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SQLiteHistoryStore:
    """
    Thread-safe SQLite store for workflow runs and their per-run artifacts.
    All access goes through one connection guarded by a lock.
    """

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path (str): Filepath of the SQLite database, or ":memory:".
        """
        self.db_path = Path(db_path)
        self._is_memory = db_path == ":memory:"
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """
        Opens the database, creating it and applying schema migrations as needed.

        Raises:
            HistoryError: If the database cannot be opened, or was written by a
                newer schema version than this code understands.
        """
        try:
            target = ":memory:"
            if not self._is_memory:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                target = str(self.db_path.resolve())

            with self._lock:
                conn = sqlite3.connect(target, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                self._migrate(conn)
                self._conn = conn
            logger.info(f"History database ready at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize history database: {e}", exc_info=True)
            raise HistoryError(f"Failed to initialize history database: {e}") from e

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            conn.close()
            raise HistoryError(
                f"History database schema v{version} is newer than supported "
                f"v{SCHEMA_VERSION}."
            )
        if version < 1:
            conn.executescript(_SCHEMA_V1)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()

    def close(self) -> None:
        """Closes the database connection, if open."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error as e:
                    logger.error(f"Error closing history database: {e}")
                finally:
                    self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise HistoryError("History database is not initialized.")
        return self._conn

    def save_run(
        self,
        run: RunSummary,
        stages: List[Dict[str, Any]],
        errors: Dict[str, str],
        artifacts: Dict[str, str],
    ) -> None:
        """
        Atomically upserts a run and its artifacts. An artifact whose content is
        unchanged is left untouched, so repeated snapshots of a long run only
        pay for what actually changed.

        Args:
            run (RunSummary): The run's summary fields.
            stages (List[Dict[str, Any]]): Per-stage status records.
            errors (Dict[str, str]): Stage name to error message.
            artifacts (Dict[str, str]): Report kind to its JSON-serialized body.

        Raises:
            HistoryError: If the write fails or the store is not initialized.
        """
        with self._lock:
            conn = self._require_conn()
            try:
                with conn:
                    conn.execute(
                        f"""
                        INSERT INTO runs ({_RUN_COLUMNS}, stages_json, errors_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (workflow_id) DO UPDATE SET
                            name = excluded.name,
                            goal = excluded.goal,
                            workflow_type = excluded.workflow_type,
                            state = excluded.state,
                            progress = excluded.progress,
                            model = excluded.model,
                            updated_at = excluded.updated_at,
                            stages_json = excluded.stages_json,
                            errors_json = excluded.errors_json
                        """,
                        (
                            run.workflow_id,
                            run.name,
                            run.goal,
                            run.workflow_type,
                            run.state,
                            run.progress,
                            run.model,
                            run.created_at,
                            run.updated_at,
                            json.dumps(stages),
                            json.dumps(errors),
                        ),
                    )
                    for kind, content in artifacts.items():
                        conn.execute(
                            """
                            INSERT INTO artifacts
                                (workflow_id, kind, content_json, size_bytes, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT (workflow_id, kind) DO UPDATE SET
                                content_json = excluded.content_json,
                                size_bytes = excluded.size_bytes,
                                updated_at = excluded.updated_at
                            WHERE artifacts.content_json != excluded.content_json
                            """,
                            (
                                run.workflow_id,
                                kind,
                                content,
                                len(content.encode("utf-8")),
                                run.updated_at,
                            ),
                        )
            except sqlite3.Error as e:
                logger.error(
                    f"Failed to save run '{run.workflow_id}': {e}", exc_info=True
                )
                raise HistoryError(f"Failed to save run: {e}") from e

    def list_runs(self, limit: int, offset: int) -> List[RunSummary]:
        """Returns run summaries, newest first."""
        with self._lock:
            rows = (
                self._require_conn()
                .execute(
                    f"SELECT {_RUN_COLUMNS} FROM runs "
                    "ORDER BY created_at DESC, workflow_id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
                .fetchall()
            )
        return [_row_to_summary(r) for r in rows]

    def count_runs(self) -> int:
        """Returns the total number of recorded runs."""
        with self._lock:
            return int(
                self._require_conn().execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            )

    def get_run(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns a run's summary, stages, errors and artifact kinds, or None.
        """
        with self._lock:
            conn = self._require_conn()
            row = conn.execute(
                f"SELECT {_RUN_COLUMNS}, stages_json, errors_json FROM runs "
                "WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if row is None:
                return None
            kinds = [
                r["kind"]
                for r in conn.execute(
                    "SELECT kind FROM artifacts WHERE workflow_id = ? ORDER BY kind",
                    (workflow_id,),
                )
            ]
        return {
            "summary": _row_to_summary(row),
            "stages": json.loads(row["stages_json"]),
            "errors": json.loads(row["errors_json"]),
            "artifact_kinds": kinds,
        }

    def get_artifact(self, workflow_id: str, kind: str) -> Optional[str]:
        """Returns an artifact's JSON body, or None if it does not exist."""
        with self._lock:
            row = (
                self._require_conn()
                .execute(
                    "SELECT content_json FROM artifacts "
                    "WHERE workflow_id = ? AND kind = ?",
                    (workflow_id, kind),
                )
                .fetchone()
            )
        return None if row is None else str(row["content_json"])

    def delete_run(self, workflow_id: str) -> bool:
        """
        Deletes a run and, by cascade, its artifacts.

        Returns:
            bool: True if a run was deleted, False if it did not exist.

        Raises:
            HistoryError: If the delete fails.
        """
        with self._lock:
            conn = self._require_conn()
            try:
                with conn:
                    cursor = conn.execute(
                        "DELETE FROM runs WHERE workflow_id = ?", (workflow_id,)
                    )
                deleted = cursor.rowcount > 0
                if deleted:
                    # SQLite keeps freed pages inside the file; compact so the
                    # disk space is actually returned to the user.
                    conn.execute("VACUUM")
                return deleted
            except sqlite3.Error as e:
                logger.error(
                    f"Failed to delete run '{workflow_id}': {e}", exc_info=True
                )
                raise HistoryError(f"Failed to delete run: {e}") from e

    def artifact_bytes_by_run(self) -> Dict[str, int]:
        """Returns each run's total stored artifact size in bytes."""
        with self._lock:
            rows = (
                self._require_conn()
                .execute(
                    "SELECT workflow_id, SUM(size_bytes) AS total "
                    "FROM artifacts GROUP BY workflow_id"
                )
                .fetchall()
            )
        return {r["workflow_id"]: int(r["total"]) for r in rows}

    def database_bytes(self) -> int:
        """Returns the on-disk size of the database file (0 for in-memory)."""
        if self._is_memory or not self.db_path.exists():
            return 0
        return self.db_path.stat().st_size
