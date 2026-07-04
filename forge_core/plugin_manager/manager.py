"""
Plugin Manager implementation for ForgeAI.
Discovers and loads enabled plugins from the plugin directory dynamically.
"""

import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from forge_core.kernel.service_registry import ServiceRegistry

from .interface import Plugin
from .service import PluginManagerService

logger = logging.getLogger("ForgeAI.PluginManager")


class PluginManager(PluginManagerService):
    """
    Concrete implementation of the PluginManagerService.
    Manages loading, caching, dynamic importing, and cleanup of plugins.
    """

    def __init__(
        self, plugin_dir: str, enabled_plugins: List[str], registry: ServiceRegistry
    ) -> None:
        """
        Initializes the Plugin Manager.

        Args:
            plugin_dir (str): Relative or absolute path to the plugins directory.
            enabled_plugins (List[str]): List of plugin folder names enabled in configuration.
            registry (ServiceRegistry): System ServiceRegistry for plugin dependency injection.
        """
        self.plugin_dir: Path = Path(plugin_dir)
        self.enabled_plugins: List[str] = enabled_plugins
        self.registry: ServiceRegistry = registry
        self._plugins: Dict[str, Plugin] = {}

    def load_plugins(self) -> None:
        """
        Scans the plugin directory and loads all configured enabled plugins dynamically.
        Warns and skips if a plugin package is missing, empty, or fails initialization.
        """
        if not self.plugin_dir.exists():
            logger.warning(
                f"Configured plugins directory does not exist: {self.plugin_dir.resolve()}"
            )
            return

        # Ensure plugin parent directory is in sys.path to resolve dynamic sub-packages
        parent_dir = str(self.plugin_dir.parent.resolve())
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Also add plugin dir itself in case plugins want direct access to their dependencies
        abs_plugin_dir = str(self.plugin_dir.resolve())
        if abs_plugin_dir not in sys.path:
            sys.path.insert(0, abs_plugin_dir)

        for plugin_name in self.enabled_plugins:
            # Check if directory exists for the plugin
            plugin_path = self.plugin_dir / plugin_name
            if not plugin_path.exists():
                logger.warning(
                    f"Enabled plugin directory is missing: {plugin_path.resolve()}. Skipping."
                )
                continue

            try:
                # Dynamic import using standard library naming convention
                module_name = f"{self.plugin_dir.name}.{plugin_name}"

                # Import module/package
                module = importlib.import_module(module_name)

                # Scan for concrete subclasses of Plugin
                plugin_cls = None
                for member_name, member_obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(member_obj)
                        and issubclass(member_obj, Plugin)
                        and member_obj is not Plugin
                    ):
                        plugin_cls = member_obj
                        break

                if not plugin_cls:
                    logger.info(
                        f"No concrete class subclassing 'Plugin' found in module: {module_name}"
                    )
                    continue

                # Instantiate and initialize
                plugin_instance: Plugin = plugin_cls()
                logger.info(
                    f"Loading plugin: {plugin_instance.name} (version {plugin_instance.version})..."
                )
                plugin_instance.initialize(self.registry)

                self._plugins[plugin_instance.name] = plugin_instance
                logger.debug(f"Plugin '{plugin_instance.name}' loaded successfully.")

            except ModuleNotFoundError as e:
                # Check if it is an empty plugin directory
                py_files = list(plugin_path.glob("**/*.py"))
                if not py_files:
                    logger.info(
                        f"Failed to import plugin '{plugin_name}': Directory is empty or contains no Python files."
                    )
                else:
                    logger.warning(
                        f"Failed to import plugin '{plugin_name}': Module not found. "
                        f"Ensure directory exists and contains valid Python package structure. Error: {e}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to load and initialize plugin '{plugin_name}': {e}",
                    exc_info=True,
                )

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """
        Retrieves a loaded plugin instance by its unique name.

        Args:
            name (str): The name of the plugin (e.g., 'PlannerPlugin').

        Returns:
            Optional[Plugin]: The plugin instance or None if not loaded.
        """
        return self._plugins.get(name)

    def get_all_plugins(self) -> List[Plugin]:
        """
        Returns a list of all currently loaded plugin instances.

        Returns:
            List[Plugin]: List of loaded plugins.
        """
        return list(self._plugins.values())

    def shutdown_all(self) -> None:
        """
        Calls shutdown on all loaded plugins and unloads them.
        """
        logger.info("Unloading and shutting down all plugins...")
        for name, plugin in list(self._plugins.items()):
            logger.info(f"Shutting down plugin: {name}...")
            try:
                plugin.shutdown()
                logger.debug(f"Plugin '{name}' shut down successfully.")
            except Exception as e:
                logger.error(
                    f"Unhandled error occurred during shutdown of plugin '{name}': {e}",
                    exc_info=True,
                )
        self._plugins.clear()
