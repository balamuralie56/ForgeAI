"""
SQLite persistence for assistant conversations, messages and change sets.

Lives in its own database file so conversations can be listed, opened and
deleted independently of workflow history, with its own schema version.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import AssistantStorageError
from .models import (
    AssistantMode,
    ChangeSet,
    ChangeSetStatus,
    CheckResult,
    Conversation,
    FileChange,
    Message,
    MessageRole,
    VerificationResult,
)

logger = logging.getLogger("ForgeAI.Plugins.Assistant.Store")

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    project_root  TEXT NOT NULL,
    check_command TEXT NOT NULL,
    auto_fix      INTEGER NOT NULL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);
CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    mode            TEXT NOT NULL,
    content         TEXT NOT NULL,
    metadata_json   TEXT NOT NULL,
    created_at      REAL NOT NULL
);
CREATE INDEX idx_messages_conversation ON messages (conversation_id, created_at);
CREATE TABLE change_sets (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    message_id        TEXT NOT NULL,
    status            TEXT NOT NULL,
    summary           TEXT NOT NULL,
    files_json        TEXT NOT NULL,
    verification_json TEXT,
    check_json        TEXT,
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL
);
CREATE INDEX idx_change_sets_conversation ON change_sets (conversation_id, created_at);
"""


def _row_to_conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        project_root=row["project_root"],
        check_command=row["check_command"],
        auto_fix=bool(row["auto_fix"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_message(row: sqlite3.Row) -> Message:
    metadata = json.loads(row["metadata_json"])
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=MessageRole(row["role"]),
        mode=AssistantMode(row["mode"]),
        content=row["content"],
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=row["created_at"],
    )


def _row_to_change_set(row: sqlite3.Row) -> ChangeSet:
    files = json.loads(row["files_json"])
    verification = (
        json.loads(row["verification_json"]) if row["verification_json"] else None
    )
    check = json.loads(row["check_json"]) if row["check_json"] else None
    return ChangeSet(
        id=row["id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        status=ChangeSetStatus(row["status"]),
        summary=row["summary"],
        files=[FileChange.from_dict(f) for f in files if isinstance(f, dict)],
        verification=(
            VerificationResult.from_dict(verification)
            if isinstance(verification, dict)
            else None
        ),
        check=CheckResult.from_dict(check) if isinstance(check, dict) else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SQLiteAssistantStore:
    """
    Thread-safe SQLite store for assistant data. All access goes through one
    connection guarded by a lock.
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
        Opens the database, creating it and applying migrations as needed.

        Raises:
            AssistantStorageError: If the database cannot be opened, or was
                written by a newer schema than this code understands.
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
            logger.info(f"Assistant database ready at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to open assistant database: {e}", exc_info=True)
            raise AssistantStorageError(
                f"Failed to open assistant database: {e}"
            ) from e

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            conn.close()
            raise AssistantStorageError(
                f"Assistant database schema v{version} is newer than supported "
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
                    logger.error(f"Error closing assistant database: {e}")
                finally:
                    self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise AssistantStorageError("Assistant database is not initialized.")
        return self._conn

    def _write(self, sql: str, params: tuple, what: str) -> int:
        """Runs one write statement in a transaction; returns affected rows."""
        with self._lock:
            conn = self._require_conn()
            try:
                with conn:
                    return conn.execute(sql, params).rowcount
            except sqlite3.Error as e:
                logger.error(f"Failed to {what}: {e}", exc_info=True)
                raise AssistantStorageError(f"Failed to {what}: {e}") from e

    def _read(self, sql: str, params: tuple) -> List[sqlite3.Row]:
        with self._lock:
            try:
                return self._require_conn().execute(sql, params).fetchall()
            except sqlite3.Error as e:
                logger.error(f"Assistant database read failed: {e}", exc_info=True)
                raise AssistantStorageError(f"Database read failed: {e}") from e

    # ── Conversations ──────────────────────────────────────────────────────

    def save_conversation(self, conversation: Conversation) -> None:
        """Inserts or updates a conversation."""
        self._write(
            """
            INSERT INTO conversations
                (id, title, project_root, check_command, auto_fix, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                title = excluded.title,
                project_root = excluded.project_root,
                check_command = excluded.check_command,
                auto_fix = excluded.auto_fix,
                updated_at = excluded.updated_at
            """,
            (
                conversation.id,
                conversation.title,
                conversation.project_root,
                conversation.check_command,
                int(conversation.auto_fix),
                conversation.created_at,
                conversation.updated_at,
            ),
            "save conversation",
        )

    def touch_conversation(self, conversation_id: str, updated_at: float) -> None:
        """Marks a conversation as having new activity."""
        self._write(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (updated_at, conversation_id),
            "update conversation",
        )

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Returns a conversation, or None."""
        rows = self._read(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        return _row_to_conversation(rows[0]) if rows else None

    def list_conversations(self, limit: int, offset: int) -> List[Conversation]:
        """Returns conversations, most recently active first."""
        rows = self._read(
            "SELECT * FROM conversations ORDER BY updated_at DESC, id "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [_row_to_conversation(r) for r in rows]

    def count_conversations(self) -> int:
        """Returns the number of stored conversations."""
        return int(self._read("SELECT COUNT(*) FROM conversations", ())[0][0])

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Deletes a conversation with its messages and change sets, then
        compacts the database so the disk space is returned.

        Returns:
            bool: True if the conversation existed.
        """
        deleted = (
            self._write(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
                "delete conversation",
            )
            > 0
        )
        if deleted and not self._is_memory:
            with self._lock:
                try:
                    self._require_conn().execute("VACUUM")
                except sqlite3.Error as e:
                    logger.error(f"Failed to compact assistant database: {e}")
        return deleted

    # ── Messages ───────────────────────────────────────────────────────────

    def add_message(self, message: Message) -> None:
        """Stores a message."""
        self._write(
            """
            INSERT INTO messages
                (id, conversation_id, role, mode, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.conversation_id,
                message.role.value,
                message.mode.value,
                message.content,
                json.dumps(message.metadata, default=str),
                message.created_at,
            ),
            "store message",
        )

    def list_messages(self, conversation_id: str) -> List[Message]:
        """Returns a conversation's messages, oldest first."""
        rows = self._read(
            "SELECT * FROM messages WHERE conversation_id = ? "
            "ORDER BY created_at, rowid",
            (conversation_id,),
        )
        return [_row_to_message(r) for r in rows]

    # ── Change sets ────────────────────────────────────────────────────────

    def save_change_set(self, change_set: ChangeSet) -> None:
        """Inserts or updates a change set."""
        self._write(
            """
            INSERT INTO change_sets
                (id, conversation_id, message_id, status, summary, files_json,
                 verification_json, check_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                message_id = excluded.message_id,
                status = excluded.status,
                summary = excluded.summary,
                files_json = excluded.files_json,
                verification_json = excluded.verification_json,
                check_json = excluded.check_json,
                updated_at = excluded.updated_at
            """,
            (
                change_set.id,
                change_set.conversation_id,
                change_set.message_id,
                change_set.status.value,
                change_set.summary,
                json.dumps([f.to_dict() for f in change_set.files]),
                (
                    json.dumps(change_set.verification.to_dict())
                    if change_set.verification
                    else None
                ),
                json.dumps(change_set.check.to_dict()) if change_set.check else None,
                change_set.created_at,
                change_set.updated_at,
            ),
            "store change set",
        )

    def get_change_set(self, change_set_id: str) -> Optional[ChangeSet]:
        """Returns a change set, or None."""
        rows = self._read("SELECT * FROM change_sets WHERE id = ?", (change_set_id,))
        return _row_to_change_set(rows[0]) if rows else None

    def list_change_sets(self, conversation_id: str) -> List[ChangeSet]:
        """Returns a conversation's change sets, oldest first."""
        rows = self._read(
            "SELECT * FROM change_sets WHERE conversation_id = ? "
            "ORDER BY created_at, rowid",
            (conversation_id,),
        )
        return [_row_to_change_set(r) for r in rows]

    # ── Storage ────────────────────────────────────────────────────────────

    def database_bytes(self) -> int:
        """Returns the on-disk size of the database file (0 for in-memory)."""
        if self._is_memory or not self.db_path.exists():
            return 0
        return self.db_path.stat().st_size

    def stats(self) -> Dict[str, Any]:
        """Returns row counts and the database size."""
        conversations = self.count_conversations()
        messages = int(self._read("SELECT COUNT(*) FROM messages", ())[0][0])
        return {
            "database_bytes": self.database_bytes(),
            "conversation_count": conversations,
            "message_count": messages,
        }
