# Plugin Manager

The ForgeAI Plugin Manager scans, loads, and initializes dynamically configured plugins at runtime.

## Core Features
1. **Dynamic Importing:**
   Utilizes standard Python libraries `importlib` and `inspect` to scan the configured plugins directory (`forge_plugins/`) for any enabled plugins listed in `forge.json`.
2. **Graceful Degradation:**
   Does not crash the boot sequence if an enabled plugin directory is empty, missing, or fails to initialize. It logs warning details and skips the loaded package.
3. **Registry Integration:**
   Upon loading a plugin, the Plugin Manager executes its initialization hook (`initialize(registry)`), allowing plugins to register custom services or hook event listeners.

## Plugin Interface
All ForgeAI plugins must inherit from the `Plugin` abstract base class and implement the required hooks:

```python
from forge_core.plugin_manager.interface import Plugin
from forge_core.kernel.service_registry import ServiceRegistry

class CustomPlugin(Plugin):
    @property
    def name(self) -> str:
        return "CustomPlugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        # Register custom services or dependencies here
        pass

    def shutdown(self) -> None:
        # Perform teardown tasks here
        pass
```
