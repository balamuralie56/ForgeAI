# Changelog

All notable changes to the ForgeAI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - Phase 1 Active Development

### Fixed
- **Python 3.14 compatibility:** Removed dead-code fallback branches in three Security Plugin rules that matched on `ast.Str`/`ast.NameConstant`, deprecated node types the parser hasn't produced since Python 3.8 and which the `ast` module removes entirely in 3.14.
- **Secrets:** The Git plugin's GitHub PAT can now be supplied via the `FORGE_GITHUB_TOKEN` environment variable instead of only `forge.json`.
- **Repo hygiene:** Repaired a corrupted, duplicated `.gitignore`; added the missing `LICENSE` (MIT) and an `.env.example` documenting all `FORGE_*` overrides.

### Added
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