"""
Interface definitions for the ForgeAI Memory Engine.
Includes definitions for Runtime Memory, Project Memory, and Persistence storage.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class RuntimeMemory(ABC):
    """
    Interface for ephemeral, in-memory state tracking.
    All methods must be thread-safe.
    """

    @abstractmethod
    def get_execution_state(self, key: str, default: Any = None) -> Any:
        """Retrieves a value from execution state."""
        pass

    @abstractmethod
    def set_execution_state(self, key: str, value: Any) -> None:
        """Sets a value in the execution state."""
        pass

    @abstractmethod
    def get_active_tasks(self) -> Dict[str, Any]:
        """Retrieves a map of all currently active tasks."""
        pass

    @abstractmethod
    def add_active_task(self, task_id: str, task_data: Any) -> None:
        """Adds or updates a task in the active tasks set."""
        pass

    @abstractmethod
    def remove_active_task(self, task_id: str) -> None:
        """Removes a task from the active tasks set."""
        pass

    @abstractmethod
    def get_loaded_plugins(self) -> Dict[str, Any]:
        """Retrieves all loaded plugins and their metadata."""
        pass

    @abstractmethod
    def register_loaded_plugin(
        self, name: str, version: str, metadata: Any = None
    ) -> None:
        """Registers a plugin as loaded."""
        pass

    @abstractmethod
    def get_project_state(self, key: str, default: Any = None) -> Any:
        """Retrieves current ephemeral project state."""
        pass

    @abstractmethod
    def set_project_state(self, key: str, value: Any) -> None:
        """Updates ephemeral project state."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clears all ephemeral runtime memory."""
        pass


class ProjectMemory(ABC):
    """
    Interface for project-specific persistent memory.
    Tracks file generation history, architecture records, and task completion.
    """

    @abstractmethod
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieves a value from project metadata."""
        pass

    @abstractmethod
    def set_metadata(self, key: str, value: Any) -> None:
        """Saves a value to project metadata."""
        pass

    @abstractmethod
    def get_generated_files(self) -> Dict[str, Any]:
        """Retrieves a dictionary of all recorded generated files."""
        pass

    @abstractmethod
    def record_generated_file(
        self, filepath: str, content_hash: str, metadata: Any = None
    ) -> None:
        """Records metadata and content hash of a generated file."""
        pass

    @abstractmethod
    def get_architecture_history(self) -> List[Any]:
        """Retrieves architectural decision logs."""
        pass

    @abstractmethod
    def add_architecture_history(self, entry: Any) -> None:
        """Adds a new record to the architecture logs."""
        pass

    @abstractmethod
    def get_completed_tasks(self) -> Dict[str, Any]:
        """Retrieves completed tasks records."""
        pass

    @abstractmethod
    def record_completed_task(self, task_id: str, task_result: Any) -> None:
        """Persists the result of a completed task."""
        pass


class PersistenceProvider(ABC):
    """
    Base interface representing connection management for database providers.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Initializes database files or connection pools."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes all active database connections."""
        pass


class KeyValueStore(PersistenceProvider):
    """
    Abstraction for standard, key-value persistent storage.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Retrieves a serialized value by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Saves a value under key."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Deletes key and its associated value."""
        pass


class VectorStore(PersistenceProvider):
    """
    Abstraction interface designed for future vector database providers.
    Do not implement concrete logic in Sprint 3.
    """

    @abstractmethod
    def add_embeddings(
        self, ids: List[str], vectors: List[List[float]], metadata: List[Dict[str, Any]]
    ) -> None:
        """Adds high-dimensional embeddings for indexing."""
        pass

    @abstractmethod
    def query_similarity(
        self, query_vector: List[float], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Queries for closest vectors based on cosine/Euclidean distance."""
        pass
