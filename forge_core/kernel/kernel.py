"""
Core Kernel implementation for ForgeAI.
Bootstraps Configuration, Logging, Service Registry, Lifecycles, Model Router, and Plugins.
"""
import logging
from typing import Optional

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.service import ConfigurationService
from forge_core.logging.engine import LoggingEngine
from forge_core.logging.service import LoggingService
from forge_core.model_router.router import ModelRouter
from forge_core.model_router.service import ModelRouterService
from forge_core.plugin_manager.manager import PluginManager
from forge_core.plugin_manager.service import PluginManagerService

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
        defaults_path: str = "config/defaults.json"
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
        self._booted: bool = False

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

        try:
            # 1. Initialize Configuration Engine
            self.config_manager = ConfigurationManager(
                config_path=str(self._config_path),
                defaults_path=str(self._defaults_path)
            )
            self._registry.register(ConfigurationService, self.config_manager)

            # 2. Initialize Logging Engine
            self.logging_engine = LoggingEngine(self.config_manager)
            self._registry.register(LoggingService, self.logging_engine.get_root_logger())

            # 3. Initialize Model Router
            self.model_router = ModelRouter(self.config_manager)
            self._registry.register(ModelRouterService, self.model_router)

            # 4. Initialize Plugin Manager
            plugin_settings = self.config_manager.get_plugin_settings()
            self.plugin_manager = PluginManager(
                plugin_dir=plugin_settings.plugin_dir,
                enabled_plugins=plugin_settings.enabled_plugins,
                registry=self._registry
            )
            self._registry.register(PluginManagerService, self.plugin_manager)

            # 5. Boot lifecycle components registered so far
            self._lifecycle_manager.initialize_all()

            # 6. Load enabled plugins
            self.plugin_manager.load_plugins()

            self._booted = True
            logger.info("ForgeAI Kernel boot complete.")

        except Exception as e:
            logger.critical(f"ForgeAI Kernel boot sequence encountered a fatal error: {e}", exc_info=True)
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
        logger.info("ForgeAI Kernel shutdown complete.")
