"""
Custom exceptions for the ForgeAI History Engine.
"""


class HistoryError(Exception):
    """Base exception for all History Engine failures."""


class InvalidSnapshotError(HistoryError):
    """Raised when a workflow snapshot is missing the fields needed to record it."""
