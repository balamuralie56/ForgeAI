"""
Custom exceptions for the ForgeAI Event Bus module.
"""


class EventBusError(Exception):
    """Base exception class for all Event Bus errors."""

    pass


class SubscriptionError(EventBusError):
    """Raised when there is an issue subscribing or unsubscribing from an event."""

    pass
