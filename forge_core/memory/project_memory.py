"""
Concrete implementation of ForgeAI Project Memory.
Delegates to a KeyValueStore provider for durable persistence.
"""

from datetime import datetime
from typing import Dict, List, Any

from .interface import KeyValueStore, ProjectMemory


class ForgeAIProjectMemory(ProjectMemory):
    """
    Persistent implementation of ProjectMemory.
    Stores and retrieves project state via a KeyValueStore.
    """

    def __init__(self, kv_store: KeyValueStore) -> None:
        """
        Initializes the Project Memory with a persistence store.

        Args:
            kv_store (KeyValueStore): Durable storage provider.
        """
        self._store = kv_store

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from project metadata.

        Args:
            key (str): Metadata key.
            default (Any): Default value if key is not found.

        Returns:
            Any: Metadata value.
        """
        val = self._store.get(f"meta:{key}")
        return val if val is not None else default

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Saves a value to project metadata.

        Args:
            key (str): Metadata key.
            value (Any): Metadata value.
        """
        self._store.set(f"meta:{key}", value)

    def get_generated_files(self) -> Dict[str, Any]:
        """
        Retrieves a dictionary of all recorded generated files.

        Returns:
            Dict[str, Any]: Map of filepath to file metadata.
        """
        files = self._store.get("files")
        return files if isinstance(files, dict) else {}

    def record_generated_file(
        self, filepath: str, content_hash: str, metadata: Any = None
    ) -> None:
        """
        Records metadata and content hash of a generated file.

        Args:
            filepath (str): The file path.
            content_hash (str): Hash of the file content.
            metadata (Any): Optional additional file metadata.
        """
        files = self.get_generated_files()
        files[filepath] = {
            "content_hash": content_hash,
            "recorded_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self._store.set("files", files)

    def get_architecture_history(self) -> List[Any]:
        """
        Retrieves architectural decision logs.

        Returns:
            List[Any]: List of structural architectural logs.
        """
        history = self._store.get("architecture")
        return history if isinstance(history, list) else []

    def add_architecture_history(self, entry: Any) -> None:
        """
        Adds a new record to the architecture logs.

        Args:
            entry (Any): Architecture decision log entry.
        """
        history = self.get_architecture_history()
        history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "entry": entry,
            }
        )
        self._store.set("architecture", history)

    def get_completed_tasks(self) -> Dict[str, Any]:
        """
        Retrieves completed tasks records.

        Returns:
            Dict[str, Any]: Map of task IDs to their results.
        """
        tasks = self._store.get("tasks")
        return tasks if isinstance(tasks, dict) else {}

    def record_completed_task(self, task_id: str, task_result: Any) -> None:
        """
        Persists the result of a completed task.

        Args:
            task_id (str): Unique task identifier.
            task_result (Any): The output or result of the task execution.
        """
        tasks = self.get_completed_tasks()
        tasks[task_id] = {
            "result": task_result,
            "completed_at": datetime.now().isoformat(),
        }
        self._store.set("tasks", tasks)
