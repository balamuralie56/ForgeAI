"""
Core data models for the ForgeAI Task Engine.
Includes the task state enumeration, retry policies, and Task representation.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TaskState(str, Enum):
    """
    Represents the operational execution states of a Task.
    """

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


@dataclass
class RetryPolicy:
    """
    Configuration policy governing how a task should be retried in case of failure.

    Attributes:
        max_retries (int): Maximum number of retry attempts. Default is 0 (no retries).
        initial_delay (float): Initial delay before retrying in seconds. Default is 1.0.
        backoff_factor (float): Multiplier applied to delay on subsequent attempts. Default is 2.0.
        jitter (bool): If True, randomized jitter is introduced to prevent herd effects. Default is True.
    """

    max_retries: int = 0
    initial_delay: float = 1.0
    backoff_factor: float = 2.0
    jitter: bool = True


class Task:
    """
    Represents an executable node in a task DAG.
    Encapsulates state, execution logic, retry behaviors, progress tracking, and metadata.
    """

    def __init__(
        self,
        task_id: str,
        name: str,
        execution_callable: Callable[..., Any],
        dependencies: Optional[List[str]] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initializes a Task instance.

        Args:
            task_id (str): Unique identifier.
            name (str): Human-readable name.
            execution_callable (Callable[..., Any]): The function or coroutine to execute.
            dependencies (Optional[List[str]]): List of task IDs this task depends on.
            retry_policy (Optional[RetryPolicy]): Rules for retry attempts on error.
            timeout (Optional[float]): Timeout limit in seconds. None indicates no limit.
            metadata (Optional[Dict[str, Any]]): Arbitrary key-value store for plugin/system context.
        """
        self.id = task_id
        self.name = name
        self.callable = execution_callable
        self.dependencies: List[str] = dependencies or []
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout = timeout
        self.metadata: Dict[str, Any] = metadata or {}

        # Live execution state fields
        self.state: TaskState = TaskState.PENDING
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.progress: float = 0.0  # Normalized progress between 0.0 and 1.0
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.current_attempt: int = 0

    def update_state(self, new_state: TaskState) -> None:
        """
        Transition the task into a new state. Sets timestamps as appropriate.

        Args:
            new_state (TaskState): The destination state.
        """
        self.state = new_state
        if new_state == TaskState.RUNNING and not self.started_at:
            self.started_at = datetime.now()
        elif new_state in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
            TaskState.SKIPPED,
        ):
            self.completed_at = datetime.now()

    def update_progress(self, progress: float) -> None:
        """
        Updates task progress. Clamps value between 0.0 and 1.0.

        Args:
            progress (float): Clamped progress percentage.
        """
        self.progress = max(0.0, min(1.0, progress))
