# ForgeAI - Privacy-First Local AI Operating System

ForgeAI is a completely local, privacy-first AI Operating System for Software Engineering. It is designed to autonomously plan software projects, design software architecture, write tests, develop applications, debug code, and review pull requests—all running locally on the user's computer without dependency on cloud AI services.

---

## 1. Vision & Core Philosophy

1. **Local First:** Everything runs locally on the user's computer with no paid APIs, no cloud inference, and no vendor lock-in.
2. **Privacy First:** No project data, source code, telemetry, or analytics ever leave the local machine.
3. **Modular Design:** Subsystems communicate through interfaces (Dependency Injection), allowing modules to be easily swapped.
4. **Production Quality:** Clean code with type hints, PEP-8 compliance, Google-style docstrings, and comprehensive testing.

---

## 2. Directory Structure

```text
ForgeAI/
├── config/                  # Configuration defaults and override schemas
├── forge_core/              # Core modules
│   ├── configuration/       # System settings manager
│   ├── logging/             # Telemetry logging engines
│   ├── kernel/              # System bootstrapper and dependency registry
│   ├── plugin_manager/      # Dynamic plugin package loader
│   ├── model_router/        # LLM client dispatcher
│   ├── event_bus/           # Thread-safe message broker (Sprint 3)
│   ├── memory/              # Short-term and long-term memory engine (Sprint 3)
│   └── task_engine/         # Directed Acyclic Graph (DAG) executor (Sprint 3)
├── forge_data/              # Runtime caches, logs, databases, and backups
├── forge_docs/              # Architectural specs and guides
├── forge_plugins/           # Dynamic plugin packages (Planner, Architect, etc.)
├── forge_tests/             # Concurrency and unit test suites
└── launcher.py              # Global boot entry point
```

---

## 3. System Architecture & Components

On startup, the **Launcher** invokes the **Kernel**, which bootstraps and registers the core engines inside the **Service Registry** dependency injection container:

```text
Launcher -> Kernel -> Service Registry
                       ├── ConfigurationService
                       ├── LoggingService
                       ├── ModelRouterService
                       ├── PluginManagerService
                       ├── EventBusService (Sprint 3)
                       ├── MemoryService (Sprint 3)
                       └── TaskEngineService (Sprint 3)
```

### Sprint 3 Engines:
- **Event Bus:** Enables decoupled, thread-safe synchronous and asynchronous event publishing/routing.
- **Memory Engine:** Coordinates ephemeral in-memory variables (Runtime Memory) and durable persistent records (Project Memory) backed by a local SQLite instance.
- **Task Engine:** Runs parallel pipelines of tasks defined as Directed Acyclic Graphs (DAGs), incorporating timeouts, exponential backoff retries, and cascading skips on failures.

---

## 4. Quick Start

### Prerequisites
- Python 3.13+

### Setup & Run
1. Create virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Start the ForgeAI OS Launcher:
   ```powershell
   python launcher.py
   ```
3. Run all tests:
   ```powershell
   python -m pytest
   ```

---

## 5. Diagnostics & Architecture

ForgeAI includes environment diagnostic utilities and architectural health check endpoints.

### Diagnostics CLI Command
To execute read-only environment validation and view dependencies without starting the runtime loop:
```powershell
python launcher.py --diagnostics
```

### System Health Endpoint
Retrieve structured system status via the Kernel service:
```python
health_report = kernel.health()
```

### Architecture Diagrams
To view the detailed Mermaid graphs illustrating component hierarchies and sequence lifecycles, refer to [runtime.md](forge_docs/architecture/runtime.md).

To regenerate the documentation:
```powershell
python scripts/generate_diagram.py
```
