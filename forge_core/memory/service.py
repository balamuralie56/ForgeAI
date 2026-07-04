"""
Service interface and concrete implementation for the Memory Engine.
Allows dynamic registration, resolution, and lifecycle hook execution.
"""

from abc import ABC, abstractmethod

from forge_core.kernel.lifecycle import LifecycleComponent
from .interface import RuntimeMemory, ProjectMemory
from .runtime_memory import ForgeAIRuntimeMemory
from .project_memory import ForgeAIProjectMemory
from .persistence import SQLitePersistenceProvider


class MemoryService(ABC):
    """
    Service registry interface for the Memory Engine.
    Provides uniform access to Runtime Memory and Project Memory.
    """

    @property
    @abstractmethod
    def runtime(self) -> RuntimeMemory:
        """
        Retrieves the Runtime Memory coordinator.

        Returns:
            RuntimeMemory: Ephemeral in-memory store.
        """
        pass

    @property
    @abstractmethod
    def project(self) -> ProjectMemory:
        """
        Retrieves the Project Memory coordinator.

        Returns:
            ProjectMemory: Persistent project store.
        """
        pass


class ForgeAIMemoryService(MemoryService, LifecycleComponent):
    """
    Concrete implementation of the MemoryService.
    Orchestrates ephemeral and persistent memory lifecycles.
    """

    def __init__(self, db_path: str = "forge_data/databases/project_memory.db") -> None:
        """
        Initializes the memory service with its constituent components.

        Args:
            db_path (str): Filepath for persistent database storage.
        """
        self._persistence = SQLitePersistenceProvider(db_path)
        self._runtime = ForgeAIRuntimeMemory()
        self._project = ForgeAIProjectMemory(self._persistence)

    @property
    def runtime(self) -> RuntimeMemory:
        """
        Retrieves the Runtime Memory coordinator.

        Returns:
            RuntimeMemory: In-memory store.
        """
        return self._runtime

    @property
    def project(self) -> ProjectMemory:
        """
        Retrieves the Project Memory coordinator.

        Returns:
            ProjectMemory: Durable key-value store.
        """
        return self._project

    def initialize(self) -> None:
        """
        Initializes the persistent memory layer (lifecycle hook).
        """
        self._persistence.initialize()

    def shutdown(self) -> None:
        """
        Closes connection pools and persists memory states (lifecycle hook).
        """
        self._persistence.close()
