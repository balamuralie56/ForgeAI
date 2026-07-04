"""
Execution controller for running individual Tasks.
Manages sync/async callables, timeouts, retries, and integrations.
"""

import asyncio
import inspect
import logging
from typing import Any

from forge_core.event_bus.interface import EventBus
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from .models import Task, TaskState
from .retry import calculate_backoff

logger = logging.getLogger("ForgeAI.TaskEngine.Executor")


class TaskExecutor:
    """
    Executes a single task, handling state transitions, notifications,
    timeouts, retries with backoff, and memory logging.
    """

    def __init__(self, event_bus: EventBus, memory: MemoryService) -> None:
        """
        Initializes the executor with dependencies.

        Args:
            event_bus (EventBus): The system Event Bus.
            memory (MemoryService): The system Memory Engine.
        """
        self._event_bus = event_bus
        self._memory = memory

    async def execute(self, task: Task) -> Any:
        """
        Runs the task with timeout and retry logic.

        Args:
            task (Task): The task to execute.

        Returns:
            Any: The return value of the execution callable.

        Raises:
            Exception: Re-raises the exception if all retries fail.
        """
        # Set to RUNNING
        task.update_state(TaskState.RUNNING)
        self._memory.runtime.add_active_task(
            task.id,
            {
                "name": task.name,
                "state": TaskState.RUNNING,
                "started_at": task.started_at.isoformat() if task.started_at else None,
            },
        )
        self._publish_event("task.started", task)
        logger.info(f"Task '{task.id}' [{task.name}] started execution.")

        max_attempts = task.retry_policy.max_retries + 1
        for attempt in range(max_attempts):
            task.current_attempt = attempt + 1
            if attempt > 0:
                task.update_state(TaskState.RETRYING)
                self._publish_event("task.retrying", task)
                logger.info(
                    f"Retrying task '{task.id}' [{task.name}] (attempt {task.current_attempt}/{max_attempts})..."
                )

            try:
                # Setup execution coroutine
                execution_coro = self._run_task_callable(task)

                # Execute with optional timeout
                if task.timeout is not None and task.timeout > 0:
                    result = await asyncio.wait_for(
                        execution_coro, timeout=task.timeout
                    )
                else:
                    result = await execution_coro

                # Success path
                task.result = result
                task.update_state(TaskState.COMPLETED)
                self._memory.runtime.remove_active_task(task.id)
                self._memory.project.record_completed_task(task.id, result)
                self._publish_event("task.completed", task)
                logger.info(f"Task '{task.id}' [{task.name}] completed successfully.")
                return result

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"Task '{task.id}' [{task.name}] timed out after {task.timeout} seconds."
                )
                task.error = e
            except Exception as e:
                logger.error(
                    f"Task '{task.id}' [{task.name}] failed: {e}", exc_info=True
                )
                task.error = e

            # If failed, compute retry delay
            if attempt < task.retry_policy.max_retries:
                delay = calculate_backoff(
                    attempt=attempt,
                    initial_delay=task.retry_policy.initial_delay,
                    backoff_factor=task.retry_policy.backoff_factor,
                    jitter=task.retry_policy.jitter,
                )
                logger.debug(
                    f"Backing off for {delay:.2f} seconds before retrying task '{task.id}'."
                )
                await asyncio.sleep(delay)

        # All attempts failed
        task.update_state(TaskState.FAILED)
        self._memory.runtime.remove_active_task(task.id)
        self._publish_event("task.failed", task)
        logger.error(
            f"Task '{task.id}' [{task.name}] failed completely after {max_attempts} attempts."
        )
        if task.error:
            raise task.error
        raise RuntimeError(f"Task '{task.id}' failed with unknown error.")

    async def _run_task_callable(self, task: Task) -> Any:
        """
        Executes the task's callable function safely, determining signature type
        and running blocking callables in separate thread pool executors.
        """
        sig = inspect.signature(task.callable)
        has_args = len(sig.parameters) > 0

        if inspect.iscoroutinefunction(task.callable):
            if has_args:
                result = await task.callable(task)
            else:
                result = await task.callable()
        else:
            if has_args:
                result = await asyncio.to_thread(task.callable, task)
            else:
                result = await asyncio.to_thread(task.callable)

        if inspect.iscoroutine(result):
            result = await result

        return result

    def _publish_event(self, event_type: str, task: Task) -> None:
        """Helper to create and publish a task event."""
        event = Event(
            event_type=event_type,
            metadata={"task_id": task.id, "attempt": task.current_attempt},
            data={
                "task_id": task.id,
                "name": task.name,
                "state": task.state,
                "progress": task.progress,
                "result": str(task.result) if task.result is not None else None,
                "error": str(task.error) if task.error is not None else None,
            },
        )
        self._event_bus.publish(event)
