"""
Core Kernel implementation for ForgeAI.
Bootstraps Configuration, Logging, Service Registry, Lifecycles, Model Router, and Plugins.
"""

import logging
import time
from typing import Optional

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.service import ConfigurationService
from forge_core.event_bus.event_bus import ForgeAIEventBus
from forge_core.event_bus.service import EventBusService
from forge_core.logging.engine import LoggingEngine
from forge_core.logging.service import LoggingService
from forge_core.memory.service import MemoryService, ForgeAIMemoryService
from forge_core.model_router.router import ModelRouter
from forge_core.model_router.service import ModelRouterService
from forge_core.plugin_manager.manager import PluginManager
from forge_core.plugin_manager.service import PluginManagerService
from forge_core.task_engine.service import TaskEngineService
from forge_core.task_engine.task_engine import ForgeAITaskEngine

from .exceptions import KernelError
from .lifecycle import LifecycleManager
from .service import Kernel
from .service_registry import ServiceRegistry

logger = logging.getLogger("ForgeAI.Kernel")


class ForgeAIKernel(Kernel):
    """
    Concrete implementation of the Kernel.
    Manages coordination, injection registry, and lifecycle sequences.
    """

    def __init__(
        self,
        config_path: str = "forge.json",
        defaults_path: str = "config/defaults.json",
    ) -> None:
        """
        Initializes the Kernel.

        Args:
            config_path (str): Filepath to the user configuration overrides.
            defaults_path (str): Filepath to system defaults.
        """
        self._registry = ServiceRegistry()
        self._lifecycle_manager = LifecycleManager()
        self._config_path = config_path
        self._defaults_path = defaults_path

        # Core engines
        self.config_manager: Optional[ConfigurationManager] = None
        self.logging_engine: Optional[LoggingEngine] = None
        self.model_router: Optional[ModelRouter] = None
        self.plugin_manager: Optional[PluginManager] = None
        self.event_bus: Optional[ForgeAIEventBus] = None
        self.memory: Optional[ForgeAIMemoryService] = None
        self.task_engine: Optional[ForgeAITaskEngine] = None
        self._booted: bool = False
        self._boot_time_ms: int = 0

    @property
    def registry(self) -> ServiceRegistry:
        """
        Retrieves the central system ServiceRegistry.

        Returns:
            ServiceRegistry: Dependency injection container.
        """
        return self._registry

    def boot(self) -> None:
        """
        Executes the atomic boot sequence of all engines and components.

        Raises:
            KernelError: If any component fail to initialize.
        """
        if self._booted:
            logger.warning("Kernel is already booted.")
            return

        start_time = time.perf_counter()
        try:
            # 1. Initialize Configuration Engine
            self.config_manager = ConfigurationManager(
                config_path=str(self._config_path),
                defaults_path=str(self._defaults_path),
            )
            self._registry.register(ConfigurationService, self.config_manager)  # type: ignore[type-abstract]

            # 2. Initialize Logging Engine
            self.logging_engine = LoggingEngine(self.config_manager)
            self._registry.register(
                LoggingService, self.logging_engine.get_root_logger()  # type: ignore[type-abstract]
            )

            # 3. Initialize Model Router
            self.model_router = ModelRouter(self.config_manager)
            self._registry.register(ModelRouterService, self.model_router)  # type: ignore[type-abstract]

            # 4. Initialize Plugin Manager
            plugin_settings = self.config_manager.get_plugin_settings()
            self.plugin_manager = PluginManager(
                plugin_dir=plugin_settings.plugin_dir,
                enabled_plugins=plugin_settings.enabled_plugins,
                registry=self._registry,
            )
            self._registry.register(PluginManagerService, self.plugin_manager)  # type: ignore[type-abstract]

            # 5. Initialize Event Bus
            self.event_bus = ForgeAIEventBus()
            self._registry.register(EventBusService, self.event_bus)  # type: ignore[type-abstract]
            self._lifecycle_manager.register(self.event_bus)

            # 6. Initialize Memory Engine
            self.memory = ForgeAIMemoryService()
            self._registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
            self._lifecycle_manager.register(self.memory)

            # 7. Initialize Task Engine
            self.task_engine = ForgeAITaskEngine(self.event_bus, self.memory)
            self._registry.register(TaskEngineService, self.task_engine)  # type: ignore[type-abstract]
            self._lifecycle_manager.register(self.task_engine)

            # 8. Boot lifecycle components registered so far
            self._lifecycle_manager.initialize_all()

            # 9. Load enabled plugins
            self.plugin_manager.load_plugins()

            self._booted = True
            self._boot_time_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(f"ForgeAI Kernel boot complete in {self._boot_time_ms} ms.")

        except Exception as e:
            logger.critical(
                f"ForgeAI Kernel boot sequence encountered a fatal error: {e}",
                exc_info=True,
            )
            # Ensure we shut down what got loaded before re-raising
            self.shutdown()
            raise KernelError(f"Kernel boot failure: {e}") from e

    def shutdown(self) -> None:
        """
        Orderly shutdown of all loaded services, plugins, and logs.
        """
        logger.info("Initiating Kernel shutdown sequence...")

        # 1. Terminate all plugins
        if self.plugin_manager:
            try:
                self.plugin_manager.shutdown_all()
            except Exception as e:
                logger.error(f"Error during plugin manager shutdown: {e}")

        # 2. Terminate registered lifecycle components
        self._lifecycle_manager.shutdown_all()

        # 3. Terminate Logging Engine last
        if self.logging_engine:
            try:
                self.logging_engine.shutdown()
            except Exception as e:
                # Logging engine is shutting down, standard print fallback
                print(f"Error during logging engine shutdown: {e}")

        self._booted = False
        self._boot_time_ms = 0
        logger.info("ForgeAI Kernel shutdown complete.")

    def health(self) -> dict:
        """
        Retrieves a structured health report containing statuses of all core services.

        Returns:
            dict: The system health report.
        """
        services = {
            "Configuration": "Ready" if self.config_manager else "Missing",
            "Logging": "Ready" if self.logging_engine else "Missing",
            "Kernel": "Ready" if self._booted else "Off",
            "PluginManager": "Ready" if self.plugin_manager else "Missing",
            "ModelRouter": "Ready" if self.model_router else "Missing",
            "EventBus": "Ready" if self.event_bus else "Missing",
            "Memory": "Ready" if self.memory else "Missing",
            "TaskEngine": "Ready" if self.task_engine else "Missing",
        }

        all_ready = all(status == "Ready" for status in services.values())
        status = "Healthy" if all_ready else "Unhealthy"

        plugins_loaded = (
            len(self.plugin_manager.get_all_plugins()) if self.plugin_manager else 0
        )

        providers = []
        if self.model_router:
            providers = list(self.model_router._providers.keys())

        from forge_core.version import __version__

        return {
            "version": __version__,
            "status": status,
            "services": services,
            "plugins_loaded": plugins_loaded,
            "providers": providers,
            "database": "SQLite" if self.memory else "None",
            "boot_time_ms": self._boot_time_ms,
        }
