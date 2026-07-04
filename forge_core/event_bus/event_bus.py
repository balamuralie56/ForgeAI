"""
Concrete implementation of the ForgeAI Event Bus.
Provides thread-safe event publishing and subscriptions.
"""

import asyncio
import inspect
import logging
import threading
import uuid
from typing import Dict, List, Callable, Any

from forge_core.kernel.lifecycle import LifecycleComponent
from .exceptions import SubscriptionError
from .models import Event
from .service import EventBusService

logger = logging.getLogger("ForgeAI.EventBus")


class Subscription:
    """
    Represents an active subscription to an event type.
    """

    def __init__(
        self, subscription_id: str, event_type: str, callback: Callable[[Event], Any]
    ) -> None:
        """
        Initializes a subscription.

        Args:
            subscription_id (str): Unique subscription ID.
            event_type (str): Event type identifier.
            callback (Callable[[Event], Any]): Callback to execute.
        """
        self.id = subscription_id
        self.event_type = event_type
        self.callback = callback


class ForgeAIEventBus(EventBusService, LifecycleComponent):
    """
    Concrete implementation of the EventBusService.
    Manages a thread-safe registry of subscribers.
    """

    def __init__(self) -> None:
        """Initializes the Event Bus."""
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._subscription_map: Dict[str, Subscription] = {}

    def initialize(self) -> None:
        """Initializes the Event Bus component (lifecycle hook)."""
        logger.info("Event Bus service initialized.")

    def shutdown(self) -> None:
        """Gracefully tears down the Event Bus and clears all subscriptions (lifecycle hook)."""
        with self._lock:
            self._subscriptions.clear()
            self._subscription_map.clear()
        logger.info("Event Bus service shut down. All subscriptions cleared.")

    def subscribe(self, event_type: str, callback: Callable[[Event], Any]) -> str:
        """
        Subscribes a callback to receive events of a specific type.

        Args:
            event_type (str): The event type to subscribe to. Use "*" for all events.
            callback (Callable[[Event], Any]): The callable invoked when the event is published.

        Returns:
            str: A unique subscription ID.

        Raises:
            SubscriptionError: If the callback is not callable.
        """
        if not callable(callback):
            raise SubscriptionError("Callback must be callable.")

        subscription_id = str(uuid.uuid4())
        subscription = Subscription(subscription_id, event_type, callback)

        with self._lock:
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            self._subscriptions[event_type].append(subscription)
            self._subscription_map[subscription_id] = subscription

        logger.debug(
            f"Registered subscriber {subscription_id} for event type: {event_type}"
        )
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """
        Removes an active subscription using its unique ID.

        Args:
            subscription_id (str): The subscription ID to cancel.

        Raises:
            SubscriptionError: If the subscription ID does not exist.
        """
        with self._lock:
            if subscription_id not in self._subscription_map:
                raise SubscriptionError(
                    f"Subscription ID '{subscription_id}' not found."
                )

            subscription = self._subscription_map.pop(subscription_id)
            event_type = subscription.event_type

            if event_type in self._subscriptions:
                self._subscriptions[event_type].remove(subscription)
                if not self._subscriptions[event_type]:
                    del self._subscriptions[event_type]

        logger.debug(f"Unsubscribed subscription ID: {subscription_id}")

    def publish(self, event: Event) -> None:
        """
        Publishes an event synchronously to all registered subscribers.
        Blocks until all synchronous subscribers have completed execution.

        Args:
            event (Event): The event instance to publish.
        """
        with self._lock:
            # Copy subscribers to allow mutations of subscriptions during dispatch
            subscribers = list(self._subscriptions.get(event.event_type, []))
            subscribers.extend(list(self._subscriptions.get("*", [])))

        for sub in subscribers:
            try:
                callback = sub.callback
                if inspect.iscoroutinefunction(callback):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Schedule on the running event loop
                            loop.create_task(callback(event))
                        else:
                            loop.run_until_complete(callback(event))
                    except RuntimeError:
                        # Fallback if no loop is configured in the thread
                        asyncio.run(callback(event))
                else:
                    callback(event)
            except Exception as e:
                logger.error(
                    f"Error in synchronous subscriber for event {event.event_type}: {e}",
                    exc_info=True,
                )

    async def publish_async(self, event: Event) -> None:
        """
        Publishes an event asynchronously.
        Schedules execution of subscribers asynchronously.

        Args:
            event (Event): The event instance to publish.
        """
        with self._lock:
            subscribers = list(self._subscriptions.get(event.event_type, []))
            subscribers.extend(list(self._subscriptions.get("*", [])))

        if not subscribers:
            return

        tasks: List[asyncio.Future[Any]] = []
        for sub in subscribers:
            callback = sub.callback
            if inspect.iscoroutinefunction(callback):
                tasks.append(asyncio.create_task(callback(event)))
            else:
                try:
                    loop = asyncio.get_running_loop()
                    # Run synchronous subscriber in executor to avoid blocking the event loop
                    tasks.append(loop.run_in_executor(None, callback, event))
                except RuntimeError:
                    # In case of no running loop (should not occur in async context)
                    callback(event)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(
                        f"Error in asynchronous subscriber for event {event.event_type}: {res}",
                        exc_info=res,
                    )
