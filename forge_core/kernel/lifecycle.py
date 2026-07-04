"""
Lifecycle management for system engines and core modules of ForgeAI.
Provides interface and coordinator to boot and shut down components deterministically.
"""
import logging
from abc import ABC, abstractmethod
from typing import List

logger = logging.getLogger("ForgeAI.LifecycleManager")


class LifecycleComponent(ABC):
    """
    Interface for components that participate in the system lifecycle.
    Each component implements startup and teardown hooks.
    """

    @abstractmethod
    def initialize(self) -> None:
        """
        Initializes the component.
        This is called during system boot.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """
        Gracefully terminates the component.
        This is called in reverse order of initialization during shutdown.
        """
        pass


class LifecycleManager:
    """
    Orchestrates the order of initialization and shutdown of all registered components.
    Ensures dependencies are resolved/booted prior to dependant components.
    """

    def __init__(self) -> None:
        """Initializes a new LifecycleManager."""
        self._components: List[LifecycleComponent] = []

    def register(self, component: LifecycleComponent) -> None:
        """
        Registers a lifecycle component.

        Args:
            component (LifecycleComponent): The component to register.
        """
        if component not in self._components:
            self._components.append(component)
            logger.debug(f"Registered lifecycle component: {type(component).__name__}")

    def initialize_all(self) -> None:
        """
        Initializes all registered components in order of registration.
        """
        for component in self._components:
            name = type(component).__name__
            logger.info(f"Initializing lifecycle component: {name}...")
            component.initialize()
            logger.debug(f"Component {name} initialized successfully.")

    def shutdown_all(self) -> None:
        """
        Gracefully shuts down all components in reverse order of registration.
        """
        for component in reversed(self._components):
            name = type(component).__name__
            logger.info(f"Shutting down lifecycle component: {name}...")
            try:
                component.shutdown()
                logger.debug(f"Component {name} shut down successfully.")
            except Exception as e:
                logger.error(
                    f"Unhandled error occurred during shutdown of {name}: {e}",
                    exc_info=True
                )
