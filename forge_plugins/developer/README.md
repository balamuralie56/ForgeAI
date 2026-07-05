# ForgeAI Developer Plugin

The Developer Plugin is an implementation compiler pipeline for ForgeAI. It translates natural language Project Plans and detailed Architecture Specifications into functional, production-ready software components (source code, configuration files, environment definitions, and database migrations).

## Features
- **Compilation Pipeline**: Uses a sequential execution flow (`ImplementationPipeline`) through 8 generator steps.
- **Unified Context**: Propagates state through a shared `ImplementationContext` payload.
- **Externalized Prompts**: Templates are stored in separate files rather than embedded in Python logic.
- **Validation Checkpoints**: Runs pre-generation checks using `ArchitectureValidator`.
- **Atomic Disk Writes**: Safe, transaction-like disk operations via `WorkspaceWriter` that rolls back all created or modified files in case of failures.
- **Progressive Lifecycle Events**: Emits detailed status messages (`started`, `progress_updated`, `file_generated`, `file_written`, `completed`, `failed`) onto the `EventBusService`.

## Usage
```python
from forge_plugins.developer.service import DeveloperService

# Resolve Developer Service from ServiceRegistry
developer = registry.resolve(DeveloperService)

# Execute the compiler pipeline to generate code assets
report = developer.implement_project(project_plan, architecture_spec)

print(f"Generated {len(report.files)} files. Status: {report.status}")
```
