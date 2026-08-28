"""
Workflow State Machine transition checker and validator.
"""

from .models import WorkflowState, Workflow
from .exceptions import WorkflowStateError


class WorkflowStateMachine:
    """
    Manages and validates state transitions for Workflows.
    """

    # Defines allowed transitions: CurrentState -> Set of AllowedNextStates
    _TRANSITIONS = {
        WorkflowState.PENDING: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
        WorkflowState.RUNNING: {
            WorkflowState.WAITING,
            WorkflowState.COMPLETED,
            WorkflowState.FAILED,
            WorkflowState.CANCELLED,
        },
        WorkflowState.WAITING: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
        WorkflowState.FAILED: set(),  # Terminal state
        WorkflowState.CANCELLED: set(),  # Terminal state
        WorkflowState.COMPLETED: set(),  # Terminal state
    }

    @classmethod
    def validate_transition(
        cls, current_state: WorkflowState, next_state: WorkflowState
    ) -> None:
        """
        Validates whether a transition from current_state to next_state is valid.

        Args:
            current_state (WorkflowState): The current state.
            next_state (WorkflowState): The target state.

        Raises:
            WorkflowStateError: If the transition is not allowed.
        """
        if current_state == next_state:
            return

        allowed_states = cls._TRANSITIONS.get(current_state, set())
        if next_state not in allowed_states:
            raise WorkflowStateError(
                f"Invalid state transition: {current_state.value} -> {next_state.value}"
            )

    @classmethod
    def transition(cls, workflow: Workflow, next_state: WorkflowState) -> None:
        """
        Transitions the workflow to next_state if valid.

        Args:
            workflow (Workflow): The workflow instance.
            next_state (WorkflowState): The state to transition to.
        """
        cls.validate_transition(workflow.state, next_state)
        workflow.state = next_state
