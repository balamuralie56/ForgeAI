# Memory Engine

The Memory Engine manages the system state of ForgeAI, exposing separate layers for short-term (Runtime Memory) and long-term (Project Memory) state tracking. It includes a database abstraction provider supporting SQLite storage.

## Core Divisions

### 1. Runtime Memory (Ephemeral)
Tracks non-persistent operational variables during active execution. This includes active executing tasks, loaded plugin metadata, and ephemeral project workspace configurations. 

### 2. Project Memory (Durable)
Tracks project histories that survive shutdowns. This includes completed task execution statistics, generated file metadata (such as hashes and output paths), and architectural decision logs.

### 3. Persistence Layer Abstraction
Decouples Memory logic from database platforms. It exposes interface contracts for:
- `KeyValueStore`: Used for standard metadata storage.
- `VectorStore`: Designed for future integration with databases like FAISS, Chroma, and pgvector.

The active default implementation uses a thread-safe `SQLitePersistenceProvider` saving key-values to `forge_data/databases/project_memory.db`.

## Example Usage

### Setting Ephemeral Runtime State
```python
from forge_core.memory import ForgeAIMemoryService

# Initialize memory service
memory = ForgeAIMemoryService()
memory.initialize()

# Set execution state
memory.runtime.set_execution_state("stage", "planning")
current_stage = memory.runtime.get_execution_state("stage") # "planning"

# Track active tasks
memory.runtime.add_active_task("task_001", {"name": "Write code"})
```

### Saving Persistent Project State
```python
# Save project metadata
memory.project.set_metadata("language", "python")

# Record generated file hashes
memory.project.record_generated_file(
    filepath="main.py",
    content_hash="d41d8cd98f00b204e9800998ecf8427e"
)

# Shutdown persists SQLite transactions and closes connection pools
memory.shutdown()
```
