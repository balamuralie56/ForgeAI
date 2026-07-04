"""
Service interface for the ForgeAI Kernel.
Core and plugin modules should depend on this interface.
"""
from abc import ABC, abstractmethod

from .service_registry import ServiceRegistry


class Kernel(ABC):
    """
    Standard interface representing the ForgeAI Kernel subsystem orchestrator.
    """

    @property
    @abstractmethod
    def registry(self) -> ServiceRegistry:
        """
        Retrieves the central system ServiceRegistry for resolving services.

        Returns:
            ServiceRegistry: Dependency injection registry.
        """
        pass

    @abstractmethod
    def boot(self) -> None:
        """
        Initiates boot sequence for all core subsystems, registries, and plugins.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """
        Triggers orderly graceful teardown of all loaded systems.
        """
        pass
