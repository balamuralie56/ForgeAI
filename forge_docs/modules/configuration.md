# Configuration Engine

The ForgeAI Configuration Engine manages system, model, and plugin settings. It strictly enforces immutability, ensuring that once the application boots, configuration states cannot be accidentally corrupted or modified by plugins.

## Core Architecture
1. **Atomic Initialization:** The `ConfigurationManager` utilizes a pure builder pattern. It is impossible for the configuration object to exist in a partially loaded or `None` state during startup.
2. **Strict Immutability:** Settings are stored in `frozen=True` Python dataclasses. Any attempt to directly modify a setting (e.g., `config.system.log_level = "DEBUG"`) will raise a `FrozenInstanceError`.
3. **Precedence Hierarchy:** Settings are resolved in the following strict mathematical order:
   - **Highest:** Environment Variables (e.g., `FORGE_MODEL`)
   - **Middle:** User Config (`forge.json`)
   - **Lowest:** System Defaults (`config/defaults.json`)

## Dependency Injection
Modules and plugins must never instantiate the `ConfigurationManager` directly. They should depend on the `ConfigurationService` interface provided by the Kernel.

## Safe Mutation
If a module needs to update the configuration at runtime (e.g., a UI settings dashboard), it must construct a new immutable configuration object using `dataclasses.replace` and submit it via the public API:

```python
from dataclasses import replace
from forge_core.configuration.service import ConfigurationService

def update_log_level(service: ConfigurationService, new_level: str) -> None:
    current_system = service.get_system_settings()
    new_system = replace(current_system, log_level=new_level)
    
    new_root_config = replace(service.get_full_config(), system=new_system)
    service.update_configuration(new_root_config)
    # The manager will automatically handle atomic file writes and backups