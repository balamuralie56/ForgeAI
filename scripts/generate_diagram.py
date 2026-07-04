"""
Architecture Diagram Generator script for ForgeAI.
Outputs structural Mermaid graphs to forge_docs/architecture/runtime.md.
"""

from pathlib import Path

RUNTIME_DOC_TEMPLATE = """# ForgeAI Runtime Architecture

This document describes the runtime service registrations, dependencies, and execution lifecycles of ForgeAI. It is automatically generated and maintained.

---

## 1. System Dependency Graph

This diagram shows the complete dependency hierarchy of the system engines. Lower layers depend only on interfaces, ensuring loose coupling.

```mermaid
graph TD
    Kernel[ForgeAIKernel] --> Configuration[Configuration Engine]
    Kernel --> Logging[Logging Engine]
    Kernel --> ModelRouter[Model Router]
    Kernel --> PluginManager[Plugin Manager]
    Kernel --> EventBus[Event Bus]
    Kernel --> Memory[Memory Engine]
    Kernel --> TaskEngine[Task Engine]

    subgraph Service Layer (D.I. Registry)
        ConfigurationService[ConfigurationService]
        LoggingService[LoggingService]
        ModelRouterService[ModelRouterService]
        PluginManagerService[PluginManagerService]
        EventBusService[EventBusService]
        MemoryService[MemoryService]
        TaskEngineService[TaskEngineService]
    end

    Configuration -.-> ConfigurationService
    Logging -.-> LoggingService
    ModelRouter -.-> ModelRouterService
    PluginManager -.-> PluginManagerService
    EventBus -.-> EventBusService
    Memory -.-> MemoryService
    TaskEngine -.-> TaskEngineService
```

---

## 2. Component Architecture Diagrams

### 2.1. Kernel & Service Registry
```mermaid
graph LR
    Kernel[ForgeAIKernel] -->|registers| Registry[ServiceRegistry]
    Registry -->|resolves| Services[Registered Services]
```

### 2.2. Configuration & Logging
```mermaid
graph TD
    Config[ConfigurationManager] -->|system log path| LogEngine[LoggingEngine]
    LogEngine -->|produces| Logs[(logs/forge.log)]
```

### 2.3. Model Router
```mermaid
graph TD
    Router[ModelRouter] -->|routes to| Providers[Model Providers]
    Providers --> Ollama[OllamaProvider]
    Providers --> OpenAI[OpenAICompatibleProvider]
```

### 2.4. Event Bus
```mermaid
graph TD
    Publisher[Event Publisher] -->|emits Event| Bus[ForgeAIEventBus]
    Bus -->|thread-safe dispatch| Subscribers[Event Subscribers]
```

### 2.5. Memory Engine
```mermaid
graph TD
    Memory[ForgeAIMemoryService] --> Runtime[ForgeAIRuntimeMemory]
    Memory --> Project[ForgeAIProjectMemory]
    Project --> DB[(SQLite Database)]
```

### 2.6. Task Engine
```mermaid
graph TD
    DAG[TaskDAG] -->|validate cyclic dfs| Scheduler[TaskScheduler]
    Scheduler -->|concurrent execute| Executor[TaskExecutor]
    Executor -->|retry/timeout| Callables[Task Callables]
```

---

## 3. Service Lifecycle Flow

```mermaid
sequenceDiagram
    participant Launcher
    participant Kernel
    participant Lifecycles
    participant Plugins

    Launcher->>Kernel: boot()
    activate Kernel
    Kernel->>Kernel: Instantiate config, logger, router, managers, event bus, memory, task engine
    Kernel->>Lifecycles: register components
    Kernel->>Lifecycles: initialize_all()
    Kernel->>Plugins: load_plugins()
    deactivate Kernel
    
    Note over Launcher, Plugins: Active Runtime Loop Execution
    
    Launcher->>Kernel: shutdown()
    activate Kernel
    Kernel->>Plugins: shutdown_all()
    Kernel->>Lifecycles: shutdown_all() (reverse order)
    Kernel->>Kernel: close log buffers
    deactivate Kernel
```
"""


def main() -> None:
    """Generates the runtime architecture markdown file."""
    output_path = Path("forge_docs/architecture/runtime.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(RUNTIME_DOC_TEMPLATE.strip(), encoding="utf-8")
    print(
        f"Successfully generated runtime architecture diagrams in: {output_path.resolve()}"
    )


if __name__ == "__main__":
    main()
