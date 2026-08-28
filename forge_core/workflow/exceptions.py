"""
Domain-specific exceptions for the ForgeAI Workflow Orchestrator.
"""


class WorkflowError(Exception):
    """Base exception class for all Workflow Orchestrator errors."""


class WorkflowStateError(WorkflowError):
    """Raised when an invalid state transition is attempted or workflow state is invalid."""


class WorkflowValidationError(WorkflowError):
    """Raised when workflow configuration, type, or arguments fail validation checks."""


class WorkflowExecutionError(WorkflowError):
    """Raised when a critical step in the workflow fails and aborts the execution."""


class WorkflowStageError(WorkflowError):
    """Raised when a specific workflow stage fails to execute."""
