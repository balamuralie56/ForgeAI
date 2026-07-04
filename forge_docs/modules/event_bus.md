# Event Bus Module

The Event Bus acts as the central decoupled communication broker within ForgeAI. It supports thread-safe, synchronous and asynchronous message publishing and subscriptions using wildcard filters and dynamic callback dispatch.

## Core Features
1. **Decoupled Architecture:** Subsystems emit events without needing knowledge of which plugins or engines are listening.
2. **Synchronous & Asynchronous Support:** Publishers can invoke listeners synchronously, blocking until all run, or asynchronously using non-blocking gather execution.
3. **Thread Safety:** Integrates lock protections (`threading.RLock`) to safe-guard subscription additions, removals, and event dispatches from concurrent contexts.
4. **Wildcard Routing:** Allows subscribers to bind to a specific event type (e.g. `task.completed`) or listen to all events using `*`.

## Event Definition
```python
from datetime import datetime
from typing import Dict, Any

class Event:
    event_type: str
    timestamp: datetime
    metadata: Dict[str, Any]
    data: Dict[str, Any]
```

## Example Usage

### Synchronous Subscription & Publishing
```python
from forge_core.event_bus import Event, ForgeAIEventBus

# Instantiate the event bus
event_bus = ForgeAIEventBus()
event_bus.initialize()

# Define subscriber callback
def handle_task_started(event: Event) -> None:
    print(f"Task started: {event.data['task_id']}")

# Subscribe and retrieve subscription ID
sub_id = event_bus.subscribe("task.started", handle_task_started)

# Publish event
event = Event(
    event_type="task.started",
    data={"task_id": "task_001"}
)
event_bus.publish(event)

# Unsubscribe when done
event_bus.unsubscribe(sub_id)
```

### Asynchronous Publishing
```python
async def handle_async_event(event: Event) -> None:
    await asyncio.sleep(0.1)
    print("Async subscriber processed event.")

# Subscribe
event_bus.subscribe("async.topic", handle_async_event)

# Publish asynchronously (non-blocking for loop)
await event_bus.publish_async(Event("async.topic"))
```
