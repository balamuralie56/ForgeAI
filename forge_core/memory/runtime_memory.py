"""
Concrete implementation of ForgeAI Runtime Memory.
Provides thread-safe in-memory storage for active task execution state.
"""

import threading
from typing import Dict, Any

from .interface import RuntimeMemory


class ForgeAIRuntimeMemory(RuntimeMemory):
    """
    In-memory, thread-safe implementation of RuntimeMemory.
    Protects read/write access to ephemeral state dictionaries using threading.RLock.
    """

    def __init__(self) -> None:
        """Initializes runtime storage dictionaries."""
        self._lock = threading.RLock()
        self._execution_state: Dict[str, Any] = {}
        self._active_tasks: Dict[str, Any] = {}
        self._loaded_plugins: Dict[str, Any] = {}
        self._project_state: Dict[str, Any] = {}

    def get_execution_state(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from execution state.

        Args:
            key (str): State key.
            default (Any): Default value if key is not found.

        Returns:
            Any: The cached state value.
        """
        with self._lock:
            return self._execution_state.get(key, default)

    def set_execution_state(self, key: str, value: Any) -> None:
        """
        Sets a value in the execution state.

        Args:
            key (str): State key.
            value (Any): Value to cache.
        """
        with self._lock:
            self._execution_state[key] = value

    def get_active_tasks(self) -> Dict[str, Any]:
        """
        Retrieves a map of all currently active tasks.

        Returns:
            Dict[str, Any]: A copy of the active tasks map.
        """
        with self._lock:
            return dict(self._active_tasks)

    def add_active_task(self, task_id: str, task_data: Any) -> None:
        """
        Adds or updates a task in the active tasks set.

        Args:
            task_id (str): Unique task identifier.
            task_data (Any): Associated task information.
        """
        with self._lock:
            self._active_tasks[task_id] = task_data

    def remove_active_task(self, task_id: str) -> None:
        """
        Removes a task from the active tasks set.

        Args:
            task_id (str): Unique task identifier.
        """
        with self._lock:
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]

    def get_loaded_plugins(self) -> Dict[str, Any]:
        """
        Retrieves all loaded plugins and their metadata.

        Returns:
            Dict[str, Any]: A copy of the loaded plugins dictionary.
        """
        with self._lock:
            return dict(self._loaded_plugins)

    def register_loaded_plugin(
        self, name: str, version: str, metadata: Any = None
    ) -> None:
        """
        Registers a plugin as loaded.

        Args:
            name (str): Plugin folder name.
            version (str): Plugin version.
            metadata (Any): Optional additional info.
        """
        with self._lock:
            self._loaded_plugins[name] = {
                "name": name,
                "version": version,
                "metadata": metadata or {},
            }

    def get_project_state(self, key: str, default: Any = None) -> Any:
        """
        Retrieves current ephemeral project state.

        Args:
            key (str): State key.
            default (Any): Default value if key is not found.

        Returns:
            Any: The cached project state value.
        """
        with self._lock:
            return self._project_state.get(key, default)

    def set_project_state(self, key: str, value: Any) -> None:
        """
        Updates ephemeral project state.

        Args:
            key (str): State key.
            value (Any): State value.
        """
        with self._lock:
            self._project_state[key] = value

    def clear(self) -> None:
        """
        Clears all ephemeral runtime memory.
        """
        with self._lock:
            self._execution_state.clear()
            self._active_tasks.clear()
            self._loaded_plugins.clear()
            self._project_state.clear()
