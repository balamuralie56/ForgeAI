"""
Custom exceptions for the ForgeAI Architect Plugin.
"""


class ArchitectError(Exception):
    """Base exception for all architectural design errors."""

    pass


class ArchitectureInferenceError(ArchitectError):
    """Raised when LLM architectural inference or parsing fails."""

    pass
