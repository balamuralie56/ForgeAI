"""
Bridges the synchronous, thread-based EventBus to async WebSocket clients.

Workflows run on a background thread (see runner.py) and publish events
through EventBus.publish(), which invokes subscriber callbacks on that same
worker thread. FastAPI's WebSocket send calls must happen on the event loop's
thread, so each connected client gets its own asyncio.Queue and the bridge
callback uses call_soon_threadsafe to hand events across that boundary safely.
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Tuple

from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event

logger = logging.getLogger("ForgeAI.API.WSManager")


def _serialize_event(event: Event) -> str:
    """Serializes an Event to a JSON string, tolerating non-JSON-safe payloads."""
    try:
        payload = {
            "event_type": event.event_type,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
        }
        return json.dumps(payload, default=str)
    except Exception as e:  # pragma: no cover - defensive, payloads are plain dicts
        logger.warning(f"Failed to serialize event {event.event_type}: {e}")
        return json.dumps({"event_type": event.event_type, "data": {}, "timestamp": ""})


class EventBroadcaster:
    """
    Fans out every published event to every connected WebSocket client's queue.
    One subscription on the EventBus serves all connections.
    """

    def __init__(self, event_bus: EventBusService) -> None:
        self._event_bus = event_bus
        self._queues: Dict[int, asyncio.Queue] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscription_id: Optional[str] = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Subscribes the broadcaster to all events, bound to the given event loop."""
        self._loop = loop
        self._subscription_id = self._event_bus.subscribe("*", self._on_event)
        logger.info("EventBroadcaster subscribed to the EventBus.")

    def stop(self) -> None:
        """Unsubscribes from the EventBus."""
        if self._subscription_id:
            self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

    def _on_event(self, event: Event) -> None:
        """Runs on whatever thread published the event; hands it to each client's queue."""
        if not self._loop or not self._queues:
            return
        message = _serialize_event(event)
        for queue in list(self._queues.values()):
            self._loop.call_soon_threadsafe(queue.put_nowait, message)

    def register(self) -> Tuple[int, asyncio.Queue]:
        """Registers a new client queue and returns its id and queue."""
        queue: asyncio.Queue = asyncio.Queue()
        client_id = id(queue)
        self._queues[client_id] = queue
        return client_id, queue

    def unregister(self, client_id: int) -> None:
        """Removes a client's queue."""
        self._queues.pop(client_id, None)
