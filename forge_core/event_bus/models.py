"""
Event models for the ForgeAI Event Bus.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any


@dataclass
class Event:
    """
    Represents an event published on the Event Bus.

    Attributes:
        event_type (str): The unique classification name of the event.
        timestamp (datetime): The datetime when the event was created.
        metadata (Dict[str, Any]): Structural or system metadata (e.g., origin, trace ID).
        data (Dict[str, Any]): Decoupled event payload.
    """

    event_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
