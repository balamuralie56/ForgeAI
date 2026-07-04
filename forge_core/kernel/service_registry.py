"""
Service Registry for dependency injection in ForgeAI.
Allows registration and resolution of system services by their interface type.
"""
from typing import Any, Dict, Type, TypeVar

from .exceptions import ServiceNotFoundError

T = TypeVar("T")


class ServiceRegistry:
    """
    Manages registration and resolution of system components/services.
    Acts as the primary dependency injection container.
    """

    def __init__(self) -> None:
        """Initializes an empty service registry."""
        self._services: Dict[Type[Any], Any] = {}

    def register(self, interface: Type[T], instance: T) -> None:
        """
        Registers a service instance under its interface type.

        Args:
            interface (Type[T]): The Type or Protocol of the service.
            instance (T): The concrete instance implementing the interface.

        Raises:
            ValueError: If instance is None.
        """
        if instance is None:
            raise ValueError("Service instance cannot be None.")
            
        self._services[interface] = instance

    def resolve(self, interface: Type[T]) -> T:
        """
        Resolves a service implementation by its interface.

        Args:
            interface (Type[T]): The interface type to resolve.

        Returns:
            T: The registered concrete service instance.

        Raises:
            ServiceNotFoundError: If the requested service is not registered.
        """
        if interface not in self._services:
            raise ServiceNotFoundError(
                f"Service representing {interface.__name__} has not been registered in the system."
            )
        return self._services[interface]
