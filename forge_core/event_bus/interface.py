"""
Interface definitions for the ForgeAI Event Bus.
"""

from abc import ABC, abstractmethod
from typing import Callable, Any

from .models import Event


class EventBus(ABC):
    """
    Standard interface representing the Event Bus subsystem.
    Handles decoupled, thread-safe message dispatch and subscriptions.
    """

    @abstractmethod
    def publish(self, event: Event) -> None:
        """
        Publishes an event synchronously to all registered subscribers.
        Blocks until all synchronous subscribers have completed execution.

        Args:
            event (Event): The event instance to publish.
        """
        pass

    @abstractmethod
    async def publish_async(self, event: Event) -> None:
        """
        Publishes an event asynchronously.
        Schedules execution of subscribers asynchronously.

        Args:
            event (Event): The event instance to publish.
        """
        pass

    @abstractmethod
    def subscribe(self, event_type: str, callback: Callable[[Event], Any]) -> str:
        """
        Subscribes a callback to receive events of a specific type.

        Args:
            event_type (str): The event type to subscribe to.
            callback (Callable[[Event], Any]): The callable invoked when the event is published.

        Returns:
            str: A unique subscription ID for subsequent unsubscription.
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        """
        Removes an active subscription using its unique ID.

        Args:
            subscription_id (str): The subscription ID to cancel.
        """
        pass
