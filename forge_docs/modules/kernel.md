# Kernel Engine

The ForgeAI Kernel is the central subsystem coordinator, managing the Service Registry, Lifecycles, and bootstrapped engines (Configuration, Logging, Model Router, Plugin Manager).

## Core Architecture
1. **Service Registry (Dependency Injection):**
   Decouples interface Protocols from their concrete class implementations (e.g. `ConfigurationService` mapping to `ConfigurationManager`). Subsystems query the registry to resolve references dynamically, preventing tight coupling.
2. **Lifecycle Management:**
   Coordinates startup initialization (`initialize()`) and graceful shutdown transitions (`shutdown()`) of all registered components in chronological and reverse-chronological order, respectively.

## Lifecycle Interface
Components implementing lifecycles must inherit from the `LifecycleComponent` interface:

```python
from abc import ABC, abstractmethod

class LifecycleComponent(ABC):
    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass
```

## Service Registration Example
```python
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.configuration.service import ConfigurationService

kernel = ForgeAIKernel()
kernel.boot()

# Resolving dependency
config = kernel.registry.resolve(ConfigurationService)
```
