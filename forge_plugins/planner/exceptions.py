"""
Custom exceptions for the ForgeAI Planner Plugin.
"""


class PlannerError(Exception):
    """Base exception for all planning errors."""

    pass


class PlanningInferenceError(PlannerError):
    """Raised when the LLM generation or parsing fails."""

    pass
