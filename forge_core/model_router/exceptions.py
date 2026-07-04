"""
Exception classes for the ForgeAI Model Router.
"""


class ModelRouterError(Exception):
    """Base exception for all errors raised by the Model Router."""

    pass


class ProviderNotFoundError(ModelRouterError):
    """Raised when a requested model provider is not registered."""

    pass


class GenerationError(ModelRouterError):
    """Raised when an LLM provider fails to generate a response."""

    pass
