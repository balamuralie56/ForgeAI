"""
Scheduler for execution of individual stages with timeout monitoring, retry rules, and event publishing.
"""

import time
import logging
import concurrent.futures
from typing import Any, Callable, Optional
from forge_core.event_bus.service import EventBusService
from forge_core.event_bus.models import Event
from .models import Workflow, WorkflowStage, WorkflowState
from .exceptions import WorkflowStageError

logger = logging.getLogger("ForgeAI.Workflow.Scheduler")


class WorkflowStageScheduler:
    """
    Executes specific workflow stages applying retry policies, timeouts, and logging.
    """

    def __init__(self, event_bus: EventBusService) -> None:
        """
        Initializes the stage scheduler.

        Args:
            event_bus (EventBusService): The central Event Bus service.
        """
        self._event_bus = event_bus

    def execute_stage(
        self,
        workflow: Workflow,
        stage: WorkflowStage,
        action: Callable[[], Any],
    ) -> Any:
        """
        Executes a stage action, applying timeouts and retry policies.

        Args:
            workflow (Workflow): The active workflow representation.
            stage (WorkflowStage): The stage definition containing retry/timeout policies.
            action (Callable[[], Any]): The actual task/callable to execute.

        Returns:
            Any: The output of the action execution.

        Raises:
            WorkflowStageError: If execution fails after all retry attempts.
        """
        stage.status = WorkflowState.RUNNING
        stage.started_at = time.time()
        stage.error = None

        self._event_bus.publish(
            Event(
                event_type="workflow.stage_started",
                data={
                    "workflow_id": workflow.id,
                    "stage_name": stage.name,
                    "retry_attempt": 0,
                },
            )
        )

        attempts = stage.retry_count + 1
        last_exception: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    f"Executing stage '{stage.name}' (Attempt {attempt}/{attempts}) for Workflow ID: {workflow.id}"
                )
                result = self._execute_with_timeout(action, stage.timeout)

                stage.status = WorkflowState.COMPLETED
                stage.completed_at = time.time()

                self._event_bus.publish(
                    Event(
                        event_type="workflow.stage_completed",
                        data={
                            "workflow_id": workflow.id,
                            "stage_name": stage.name,
                            "attempt": attempt,
                        },
                    )
                )
                return result

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Stage '{stage.name}' failed on attempt {attempt} for Workflow ID: {workflow.id}. Error: {e}"
                )

                if attempt < attempts:
                    self._event_bus.publish(
                        Event(
                            event_type="workflow.retry",
                            data={
                                "workflow_id": workflow.id,
                                "stage_name": stage.name,
                                "failed_attempt": attempt,
                                "max_attempts": attempts,
                                "error": str(e),
                            },
                        )
                    )
                    time.sleep(stage.retry_delay)

        # If we reach here, all retry attempts failed
        stage.status = WorkflowState.FAILED
        stage.completed_at = time.time()
        stage.error = str(last_exception)

        logger.error(
            f"Stage '{stage.name}' failed after all {attempts} attempts. Error: {last_exception}"
        )

        raise WorkflowStageError(
            f"Stage '{stage.name}' failed after {attempts} attempts. Inner error: {last_exception}"
        ) from last_exception

    def _execute_with_timeout(
        self, action: Callable[[], Any], timeout_seconds: float
    ) -> Any:
        """Executes a callable inside a thread pool with a timeout constraint."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(action)
            try:
                return future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError as te:
                raise TimeoutError(
                    f"Action timed out after {timeout_seconds} seconds."
                ) from te
