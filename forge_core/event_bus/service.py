"""
Service interface representation for the Event Bus.
Allows registration and resolution in the Kernel Service Registry.
"""

from .interface import EventBus


class EventBusService(EventBus):
    """
    Service registry interface for the Event Bus.
    Plugins and services should resolve this service type from the registry.
    """

    pass
