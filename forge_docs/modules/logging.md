# Logging Engine

The ForgeAI Logging Engine provides a non-blocking, highly concurrent telemetry system. Because ForgeAI handles autonomous LLM generation tasks, standard synchronous file logging would create severe I/O bottlenecks.

## Core Features
1. **Queue-Based Non-Blocking Architecture:** Writing to the logger pushes the payload to a queue. A background thread processes the file I/O concurrently.
2. **Context Binding:** Allows tagging logs with metadata (like `task_id`) that persists down the execution chain.
3. **Dual Sinks:**
   - **Console:** Standard output for development and system health monitoring.
   - **File (JSONL):** Newline-delimited JSON saved to `forge_data/logs/forge.log` for machine parsing and querying by the Memory Engine.

## Dependency Injection
Never instantiate the `LoggingEngine` inside a plugin. Rely on the `LoggingService` interface provided by the Kernel.

## Rotation Strategy
Files rotate automatically at 10 MB, keeping a maximum of 5 historical logs, capping the total logging disk footprint at ~60 MB to prevent storage exhaustion.