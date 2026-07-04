# Changelog

All notable changes to the ForgeAI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-07-04

### Added
- **Central Versioning:** Created `forge_core/version.py` defining central metadata attributes, referencing them in the Launcher and Kernel.
- **Kernel Health Reports:** Implemented `Kernel.health()` returning system health reports, service states, active providers, and boot metrics.
- **Diagnostics CLI Command:** Introduced `python launcher.py --diagnostics` to dump environmental information in a safe, read-only manner.
- **Architecture Diagram Generator:** Created `scripts/generate_diagram.py` to auto-maintain Mermaid graphs in `forge_docs/architecture/runtime.md`.
- **CI Enhancements:** Configured `.coveragerc` rules, `requirements.txt`, and `.github/workflows/ci.yml` to check formatting, linting, typing, and enforce a 90% test coverage minimum.

### Changed
- **Plugin Loading Warnings:** Downgraded logs from `WARNING` to `INFO` for empty plugin directories.

## [0.3.0] - 2026-07-04

### Added
- **Event Bus:** Implemented thread-safe `ForgeAIEventBus` supporting synchronous/asynchronous publishing and wildcard subscriptions (`*`).
- **Memory Engine:** Created `ForgeAIRuntimeMemory` for short-term in-memory tracking and `ForgeAIProjectMemory` backed by a key-value store for durable long-term logs.
- **SQLite Persistence:** Added `SQLitePersistenceProvider` to persist project memory database locally under `forge_data/databases/project_memory.db`.
- **Task Engine:** Implemented `ForgeAITaskEngine`, `TaskExecutor`, and `TaskScheduler` to concurrently schedule and execute DAG task configurations.
- **Fault-Tolerance Retries:** Integrated task-level retry policies with exponential backoff and randomized delay jitter.
- **Cascading Skips:** Automated recursive state skipping on all child nodes when a parent dependency fails.
- **Kernel Integration:** Bootstrapped the Event Bus, Memory, and Task Engine directly into the Kernel lifecycle (`initialize()` and `shutdown()`) and `ServiceRegistry`.
- **Unit and Concurrency Tests:** Added unit and concurrency tests for Event Bus, Memory Engine, and Task Engine under `forge_tests/`.
- **Documentation:** Added module documentation under `forge_docs/modules/` and Sprint 3 Technical Design.

## [Unreleased] - Phase 1 Active Development

### Added
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