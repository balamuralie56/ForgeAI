"""
Persistence layer implementations for the ForgeAI Memory Engine.
Includes the thread-safe SQLitePersistenceProvider.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from .interface import KeyValueStore

logger = logging.getLogger("ForgeAI.Memory.Persistence")


class SQLitePersistenceProvider(KeyValueStore):
    """
    SQLite-based Key-Value persistent store.
    Uses json serialization for values and synchronizes operations with a thread lock.
    """

    def __init__(self, db_path: str = "forge_data/databases/project_memory.db") -> None:
        """
        Initializes the provider configuration.

        Args:
            db_path (str): Filepath to the SQLite database.
        """
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """
        Initializes the SQLite database and creates the schema.
        Ensures the parent directories exist if not using an in-memory database.
        """
        try:
            db_conn_str = str(self.db_path)
            if db_conn_str != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                db_conn_str = str(self.db_path.resolve())

            with self._lock:
                # check_same_thread=False allows cross-thread query dispatching, guarded by our lock.
                self._conn = sqlite3.connect(db_conn_str, check_same_thread=False)
                cursor = self._conn.cursor()
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS project_memory ("
                    "key TEXT PRIMARY KEY, "
                    "value TEXT"
                    ")"
                )
                self._conn.commit()
            logger.info(f"SQLite DB initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}", exc_info=True)
            raise

    def close(self) -> None:
        """
        Gracefully closes the SQLite database connection.
        """
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                    logger.debug("SQLite database connection closed.")
                except Exception as e:
                    logger.error(f"Error closing SQLite database: {e}")
                finally:
                    self._conn = None

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value associated with key.

        Args:
            key (str): The storage key.

        Returns:
            Optional[Any]: The deserialized JSON object, or None if key is missing.
        """
        with self._lock:
            if not self._conn:
                raise RuntimeError("SQLite database is not initialized.")
            try:
                cursor = self._conn.cursor()
                cursor.execute("SELECT value FROM project_memory WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
                return None
            except Exception as e:
                logger.error(f"Error retrieving key '{key}' from SQLite: {e}")
                return None

    def set(self, key: str, value: Any) -> None:
        """
        Stores a value under the given key, overwriting it if it exists.

        Args:
            key (str): The storage key.
            value (Any): Any JSON-serializable Python data type.
        """
        with self._lock:
            if not self._conn:
                raise RuntimeError("SQLite database is not initialized.")
            try:
                cursor = self._conn.cursor()
                serialized = json.dumps(value)
                cursor.execute(
                    "INSERT OR REPLACE INTO project_memory (key, value) VALUES (?, ?)",
                    (key, serialized),
                )
                self._conn.commit()
            except Exception as e:
                logger.error(f"Error setting key '{key}' in SQLite: {e}", exc_info=True)
                raise

    def delete(self, key: str) -> None:
        """
        Removes the key and its value from the store.

        Args:
            key (str): The storage key.
        """
        with self._lock:
            if not self._conn:
                raise RuntimeError("SQLite database is not initialized.")
            try:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM project_memory WHERE key = ?", (key,))
                self._conn.commit()
            except Exception as e:
                logger.error(f"Error deleting key '{key}' in SQLite: {e}")
                raise
