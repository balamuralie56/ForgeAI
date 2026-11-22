# ForgeAI - Privacy-First Local AI Operating System

ForgeAI is a completely local, privacy-first AI Operating System for Software Engineering. It is designed to autonomously plan software projects, design software architecture, write tests, develop applications, debug code, and review pull requests—all running locally on the user's computer without dependency on cloud AI services.

**Current state: v0.9.5.** Core runtime, the 8 build plugins (Planner, Architect, Developer, Tester, Documentation, Security, Reviewer, Git), the local coding Assistant, the FastAPI backend, and the React frontend are implemented and covered by 492 passing tests. The sections below are written to match what actually runs today, not the long-term vision — see [Section 6](#6-honest-project-status) for what's finished, what's a known gap, and what hasn't been started.

---

## 0. See It Run: the BUILD_ONLY Demo

The fastest way to see ForgeAI actually work end-to-end is the `BUILD_ONLY` workflow: **Planner → Architect → Developer**. Given a one-line goal, it produces a structured project plan, an architecture specification, and generated project files on disk — no cloud model, no manual scaffolding.

Proof this isn't aspirational: [`forge_workspace/todo_pipeline_demo/`](forge_workspace/todo_pipeline_demo) is a real output of this exact pipeline — generated `api.py`, `database.py`, `models.py`, `config.py`, plus the unit/integration/regression/smoke tests the Tester plugin wrote for them, with `__pycache__` present, meaning those generated tests were actually executed, not just written to disk.

To run it yourself (requires [Ollama](https://ollama.com) running locally with a model pulled, e.g. `ollama pull qwen2.5-coder`):

```powershell
# Terminal 1 - backend
uvicorn forge_api.main:app --reload --port 8420
```

```powershell
# Terminal 2 - frontend
cd forge_frontend
npm install
npm run dev
```

Then either use the web UI, or trigger it directly against the API:

```powershell
curl -X POST http://localhost:8420/api/workflows -H "Content-Type: application/json" -d "{\"goal\": \"A CLI todo list manager with add, remove, and list commands\", \"workflow_type\": \"BUILD_ONLY\"}"
```

Poll `GET /api/workflows/{workflow_id}` for progress, then `GET /api/reports/project_plan` and `GET /api/reports/architecture_specification` for the Planner/Architect output, and `GET /api/workflows/{workflow_id}/files` to see what the Developer plugin wrote to the workspace. There is currently no CLI for this — see Section 6.

### Work on your own code: the Assistant
Switch the top bar of the web UI to **Assistant**, pick a project folder and (ideally) a check command such as `python -m pytest -q`, then:
- **Ask** questions about the code ("where is the config loaded?", "why does @test_store.py fail?").
- **Change** code ("add a `--verbose` flag to @cli.py"). ForgeAI proposes a diff. Edits that don't match the files or would break imports or names go back to the model automatically. Nothing is written until you click **Apply change** (then your check runs), and **Undo change** restores the files. Optional auto-fix applies changes, runs the check and fixes failures by itself.

It runs on the same local model. With `qwen2.5-coder:3b` on an iGPU, a focused change takes about 30–90 s. See [assistant.md](forge_docs/modules/assistant.md) for what it checks and what it can't do.

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
├── forge_core/               # Core modules
│   ├── configuration/        # System settings manager
│   ├── logging/               # Telemetry logging engines
│   ├── kernel/                 # System bootstrapper and dependency registry
│   ├── plugin_manager/        # Dynamic plugin package loader
│   ├── model_router/           # LLM client dispatcher (Ollama + OpenAI-compatible)
│   ├── event_bus/               # Thread-safe message broker
│   ├── memory/                   # Short-term and long-term memory engine
│   ├── task_engine/              # Directed Acyclic Graph (DAG) executor
│   └── workflow/                  # Stage orchestrator / state machine / scheduler
├── forge_plugins/             # Planner, Architect, Developer, Tester, Documentation,
│                               # Security, Reviewer, Git, Assistant - each with service/models/components
├── forge_api/                  # FastAPI backend (REST + WebSocket) exposing the Kernel/Workflow
├── forge_frontend/             # React multi-tab workbench consuming the API
├── forge_data/                  # Runtime caches, logs, databases, and backups
├── forge_docs/                   # Architectural specs, ROADMAP, and guides
├── forge_workspace/               # Generated project output from completed workflow runs
├── forge_tests/                    # Unit, integration, and concurrency test suites
└── launcher.py                     # Boot entry point (kernel diagnostics; no workflow CLI yet)
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
                       ├── EventBusService
                       ├── MemoryService
                       ├── TaskEngineService
                       └── WorkflowService
```

The **FastAPI backend** (`forge_api`) sits on top of the same Kernel/Service Registry and exposes it over REST + a WebSocket event stream to the **React frontend**; every plugin call a workflow stage makes goes through the real `ModelRouterService` (Ollama or an OpenAI-compatible endpoint), not a mock.

### Core Engines
- **Event Bus:** Decoupled, thread-safe synchronous and asynchronous event publishing/routing.
- **Memory Engine:** Ephemeral in-memory state (Runtime Memory) and durable persistent records (Project Memory) backed by local SQLite.
- **Task Engine:** Runs task pipelines as Directed Acyclic Graphs (DAGs), with timeouts, exponential backoff retries, and cascading skips on failure.
- **History Engine:** Keeps a per-run record of every workflow and the reports it produced in its own SQLite database, so earlier runs are no longer overwritten by later ones. Exposed through `/api/history/*` (list, open, delete, storage usage) — see [history.md](forge_docs/modules/history.md). The React UI shows it in a History sidebar: reopen or delete past runs and see storage used.
- **Workflow Orchestrator:** Sequences plugin stages (e.g. Planner → Architect → Developer) into a named `WorkflowType`, persisting state so a run can resume after interruption.

### AI Plugins
Planner, Architect, Developer, Tester, Documentation, Security, Reviewer, and Git — see [Section 0](#0-see-it-run-the-build_only-demo) for the Planner/Architect/Developer path, and [Section 6](#6-honest-project-status) for what each plugin actually covers today.

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

---

## 6. Honest Project Status

ForgeAI is far enough along to be worth showing, and far enough from done that it's worth saying so plainly.

**Finished** — real implementation, covered by passing tests:
- Core runtime: Kernel, Configuration, Logging, Event Bus, Memory, Plugin Manager, Task Engine, Model Router, Workflow Orchestrator.
- All 8 plugins: Planner, Architect, Developer, Tester, Documentation, Security, Git, Reviewer.
- The FastAPI backend and React frontend, wired to the real services (no mocked responses).
- The `BUILD_ONLY` workflow (Section 0) runs end-to-end today; `forge_workspace/todo_pipeline_demo` is a real artifact proving it.
- The Assistant: a local coding assistant for existing projects (questions, and checked, reversible changes with test-driven auto-fix). It is only as capable as the local model: a 3B model handles focused single-file changes well and struggles with multi-file refactors. The checks catch broken edits, not wrong ideas. See [assistant.md](forge_docs/modules/assistant.md).
- The Developer plugin statically validates the code it generates (without executing it) and reports `VALIDATION_FAILED` instead of `SUCCESS` when the code will not import or run. Running the workflow does not mean the generated code is correct: with small local models (e.g. `qwen2.5-coder:3b`) it often isn't, and the validation panel in the Files tab says so. See [code_validation.md](forge_docs/modules/code_validation.md).

**Known, intentional gap:**
- The Reviewer plugin's Liskov Substitution (L) check is explicitly not implemented — it needs cross-class contract analysis the current rule interface can't do. Documented in `forge_docs/ROADMAP.md`, not an oversight.

**Not started:**
- There is no CLI for triggering a workflow — today that's done through the FastAPI backend (directly, or via the React frontend). `launcher.py` only boots the kernel and runs diagnostics.
- v1.0.0 "Production Release" is the only remaining roadmap milestone; distributed execution, model collaboration, self-improvement, and a plugin marketplace are long-term ideas with no code behind them yet.

See `AGENTS.md` Sections 5-6 for the full sprint-by-sprint breakdown.
