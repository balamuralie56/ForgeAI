"""
Interface definitions for ForgeAI plugins.
All system plugins must subclass the Plugin interface.
"""

from abc import ABC, abstractmethod

from forge_core.kernel.service_registry import ServiceRegistry


class Plugin(ABC):
    """
    Abstract base class that all ForgeAI plugins must implement.
    Defines the lifecycle hooks and properties required for integration.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The unique name of the plugin (e.g., 'PlannerPlugin').

        Returns:
            str: Plugin name.
        """
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """
        The semantic version of the plugin (e.g., '1.0.0').

        Returns:
            str: Semantic version.
        """
        pass

    @abstractmethod
    def initialize(self, registry: ServiceRegistry) -> None:
        """
        Initializes the plugin when loaded.
        Allows registering custom services or event listeners.

        Args:
            registry (ServiceRegistry): The central system registry.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """
        Graceful cleanup callback executed during system shutdown.
        """
        pass
