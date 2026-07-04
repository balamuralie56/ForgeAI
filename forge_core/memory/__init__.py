"""
Memory Engine module for ForgeAI.
Manages ephemeral execution state and durable project-specific persistence.
"""

from .interface import (
    RuntimeMemory,
    ProjectMemory,
    PersistenceProvider,
    KeyValueStore,
    VectorStore,
)
from .runtime_memory import ForgeAIRuntimeMemory
from .project_memory import ForgeAIProjectMemory
from .persistence import SQLitePersistenceProvider
from .service import MemoryService, ForgeAIMemoryService

__all__ = [
    "RuntimeMemory",
    "ProjectMemory",
    "PersistenceProvider",
    "KeyValueStore",
    "VectorStore",
    "ForgeAIRuntimeMemory",
    "ForgeAIProjectMemory",
    "SQLitePersistenceProvider",
    "MemoryService",
    "ForgeAIMemoryService",
]
