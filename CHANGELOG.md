# Changelog

All notable changes to the ForgeAI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - Phase 1 Active Development

### Fixed
- **Assistant edit handling:** fixes for failures seen when testing the assistant on ForgeAI's own code with `qwen2.5-coder:3b`.
  - The parser accepts a `>>>>>>> REPLACE` written in place of, or just before, the divider. It takes code written after a closing marker that came too early, and refuses a second divider instead of writing it into the file.
  - When REPLACE restates the lines after a too-short SEARCH, those lines are replaced rather than duplicated.
  - A whole-file rewrite must keep every module-level statement. This catches a dropped `if __name__ == "__main__":` guard that the tests didn't cover.
  - A final try that doesn't parse is reported as a failure, not proposed.
  - The last try asks for complete function or class definitions instead of edit blocks.
  - A reply that starts repeating itself is cut off and retried.
  - A model-runner crash before any output is retried once.
  - Naming a file with `@` limits the code shown for an edit to that file, which keeps prompts short.
- **Interrupted runs:** runs left PENDING/RUNNING/WAITING when the server stopped are now marked CANCELLED at API startup (with the interrupted stage and an "interrupted" error recorded), instead of showing as running forever with deletion disabled in the UI.
- **Developer status:** the Developer plugin no longer reports `SUCCESS` for code that cannot run; see Code Validation below.
- **Workflow history ordering:** the orchestrator now records a run in history before its status becomes visible in project memory, so a client that sees a stage as completed can always read that stage's report.
- **Python 3.14 compatibility:** Removed dead-code fallback branches in three Security Plugin rules that matched on `ast.Str`/`ast.NameConstant`, deprecated node types the parser hasn't produced since Python 3.8 and which the `ast` module removes entirely in 3.14.
- **Secrets:** The Git plugin's GitHub PAT can now be supplied via the `FORGE_GITHUB_TOKEN` environment variable instead of only `forge.json`.
- **Repo hygiene:** Repaired a corrupted, duplicated `.gitignore`; added the missing `LICENSE` (MIT) and an `.env.example` documenting all `FORGE_*` overrides.

### Added
- **Assistant Plugin (local coding assistant):** a new `assistant` plugin and **Assistant** view in the frontend for working on existing projects. Ask questions about the code, or describe a change: ForgeAI finds the relevant code (BM25 search, `@file` mentions, traceback paths), streams the model's reply, applies SEARCH/REPLACE edits in memory with tolerant matching, rejects unusable edits, statically checks the project before and after (reusing the Developer validator, plus a missing-`self`-attribute check), and retries with the exact problems. It then proposes a diff to apply, discard or undo. If a check command is set (e.g. `python -m pytest -q`), it runs after applying; when you describe a failure, it runs first so the model sees the real error; and in auto-fix mode failures feed further rounds. Replies that ignore the edit format but restate a whole file or whole definitions are accepted only when nothing existing is dropped. Conversations, messages and change sets are stored in `forge_data/databases/forge_assistant.db`. The `/api/assistant/*` endpoints require an `X-ForgeAI-Client` header and a loopback host. Nothing the model writes is executed. See `forge_docs/modules/assistant.md`.
- **Streaming chat (Model Router):** `ModelProvider.stream_chat` / `ModelRouterService.stream_chat`, with Ollama NDJSON and OpenAI-compatible SSE streaming. Providers without streaming inherit a single-chunk fallback, so existing providers keep working.
- **Configuration:** new `assistant` section (model, context window, reply limits, retry and fix-round limits, check timeout, indexing limits) and `FORGE_ASSISTANT_MODEL` / `FORGE_ASSISTANT_CONTEXT_TOKENS` overrides.
- **Code Validation (Developer Plugin):** a `CodeValidationStep` statically validates every generated file without executing it - Python syntax, JSON/TOML, unresolvable or relative-from-top-level imports, names imported but not defined in the target module, undefined names, undeclared third-party dependencies, leftover stubs/placeholder comments, and duplicates. `ImplementationReport.status` is now `SUCCESS`, `SUCCESS_WITH_WARNINGS` or `VALIDATION_FAILED`, and the report carries a `validation` result (also in `implementation_report.md`, a `developer.validated` event, and a panel in the UI's Files tab). Validated against the real broken `qwen2.5-coder:3b` output that was previously reported as SUCCESS. See `forge_docs/modules/code_validation.md`.
- **History Engine:** New `forge_core/history` package with a `HistoryService` (registered in the Kernel) backed by a dedicated `forge_history.db`. Every workflow run now keeps its own copy of each plugin report, so a later run no longer overwrites an earlier one. Captured by the `WorkflowOrchestrator` whenever it persists workflow state; skipped when no history service is registered, and a history failure never fails a workflow.
- **History API:** `GET /api/history/runs`, `GET /api/history/runs/{id}`, `GET /api/history/runs/{id}/artifacts/{kind}`, `DELETE /api/history/runs/{id}` (refuses runs still in progress), and `GET /api/history/storage`.
- **History sidebar (frontend):** reopen or delete past runs, see storage used, and view any run's own reports in the existing tabs. Report text is rendered defensively and a per-tab error boundary stops an unexpected report shape from blanking the app (found when `qwen2.5-coder:3b` returned table columns as `{type, description}` objects).
- **Project Memory:** `ProjectMemory.delete_metadata()` to remove a stored key.
- **Security Plugin:** Implemented dynamic Security plugin checking python files for AST vulnerabilities (eval, exec, shell commands, pickling, weak crypto, temp files, hardcoded passwords, SQL injection), checking requirements.txt for CVE dependencies, and scanning for copyleft licenses.
- **SARIF Standard Export:** Formatted reports to industry-standard SARIF JSON reports, alongside markdown and standard report JSON deliverables.
- **Release Quality Gates:** Integrated quality gates checking maximum critical/high findings count and overall risk scores, halting git commits and pipeline release if exceeded.
- **Workflow Orchestrator:** Implemented central `WorkflowService` and `WorkflowOrchestrator` to coordinate planning, design, implementation, testing, documenting, and git pipelines in a unified state-machine flow with retries, timeout policies, event-bus triggers, and crash recovery.
- **Developer Plugin:** Introduced a new plugin at `forge_plugins/developer/` with modular generation architecture.
- **Implementation Context:** Created `ImplementationContext` state container for generator pipeline data sharing.
- **Orchestration Pipeline:** Implemented `ImplementationPipeline` to sequentially coordinate dependency, environment, config, database, API, backend, frontend, and report steps.
- **Prompt Template Engine:** Moved prompts out of Python and into external text templates under `developer/prompts/`.
- **Pre-generation Validation:** Introduced `ArchitectureValidator` to ensure project plans and architectural specifications are fully compatible before code generation begins.
- **Durable Atomic Writer:** Added `WorkspaceWriter` that atomically writes generated code assets to the target workspace and executes automatic file cleanups/rollbacks upon failure.
- **Comprehensive Lifecycle Events:** Emitted structured events (`started`, `progress_updated`, `file_generated`, `file_written`, `completed`, `failed`) across the system event bus.
- **Robust Test Coverage:** Added unit, integration, memory, validation, and rollback tests achieving 91% coverage.

- **Service Registry:** Implemented `ServiceRegistry` to serve as the system-wide dependency injection container.
- **Lifecycle Manager:** Added `LifecycleManager` to orchestrate orderly engine startup and teardown sequences.
- **Kernel Orchestration:** Implemented `ForgeAIKernel` class to manage dependencies and system boot sequence.
- **Plugin Manager:** Added dynamic plugin package scanner and loader using `importlib` and `inspect` under `forge_plugins/`.
- **Model Router:** Implemented `ModelRouter` to resolve LLM clients dynamically.
- **Model Providers:** Created `OllamaProvider` and `OpenAICompatibleProvider` relying solely on standard library `urllib` calls.
- **System Launcher Integration:** Refactored `launcher.py` to bootstrap the Kernel, displaying dynamic plugin counts and Kernel ready status on boot.
- **Unit and Integration Tests:** Created comprehensive test suites (`test_kernel.py`, `test_plugin_manager.py`, `test_model_router.py`), achieving 100% pass rate.
- **Documentation:** Added module documentation guides for Kernel, Plugin Manager, and Model Router under `forge_docs/modules/`.
- **System Launcher:** Implemented `launcher.py` to serve as the global application entry point.
- **Environment Bootstrapper:** Launcher automatically guarantees and provisions the `forge_data/` and `forge_workspace/` directory trees on boot.
- **Boot Validation:** Added a formatted boot banner to verify active component status.
- **Logging Engine:** Implemented a queue-based, non-blocking telemetry system with dual sinks (Console and JSON file rotation).
- **Logging Interfaces:** Added `LoggingService` Protocol to decouple plugins from concrete implementations.
- **Configuration Engine:** Implemented `ConfigurationManager` to handle defaults, user overrides, and environment variables.
- **Data Models:** Added `frozen=True` dataclasses for strict typing and immutability.
- **Test Suites:** 100% concurrency and edge-case test coverage for Logging, Configuration, and Launcher boot sequence.

### Changed
- **Launcher Boot Delegation:** Offloaded Engine and Logger initialization from Launcher to Kernel.
- **Configuration Validation:** Moved schema logic out of constructors and into strict validation blocks.
- **Configuration Engine Refactor:** `_build_configuration()` method is now a pure function, guaranteeing atomic initialization.
- **Backup Strategy:** Standardized backup naming conventions (e.g., `forge.dev.json` backs up to `forge.dev.json.bak`).