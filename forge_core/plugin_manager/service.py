"""
Service interface for the ForgeAI Plugin Manager.
Core components and plugins should depend on this interface, not concrete classes.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .interface import Plugin


class PluginManagerService(ABC):
    """
    Interface managing loading, unloading, and retrieving plugins in the system.
    """

    @abstractmethod
    def load_plugins(self) -> None:
        """
        Scans the plugin directory and loads all configured/enabled plugins.
        """
        pass

    @abstractmethod
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """
        Retrieves a loaded plugin instance by its unique name.

        Args:
            name (str): The name of the plugin.

        Returns:
            Optional[Plugin]: The plugin instance, or None if not loaded.
        """
        pass

    @abstractmethod
    def get_all_plugins(self) -> List[Plugin]:
        """
        Returns a list of all currently loaded plugin instances.

        Returns:
            List[Plugin]: List of loaded plugins.
        """
        pass

    @abstractmethod
    def shutdown_all(self) -> None:
        """
        Unloads and calls shutdown on all loaded plugins.
        """
        pass
