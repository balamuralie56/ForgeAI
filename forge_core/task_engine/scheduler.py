"""
Asynchronous concurrent Task Scheduler for DAG execution in ForgeAI.
Manages queues, resolves readiness, executes parallel jobs, and cascades skips.
"""

import asyncio
import logging
from typing import Dict, Any

from forge_core.event_bus.interface import EventBus
from forge_core.event_bus.models import Event
from forge_core.memory.service import MemoryService
from .models import Task, TaskState
from .dag import TaskDAG
from .executor import TaskExecutor

logger = logging.getLogger("ForgeAI.TaskEngine.Scheduler")


class TaskScheduler:
    """
    Manages concurrent DAG execution, checks dependency status,
    controls capacity (concurrency slots), and handles cancellations.
    """

    def __init__(
        self, event_bus: EventBus, memory: MemoryService, concurrency_limit: int = 5
    ) -> None:
        """
        Initializes the Task Scheduler.

        Args:
            event_bus (EventBus): System message broker.
            memory (MemoryService): System memory service.
            concurrency_limit (int): Max concurrent task executes allowed.
        """
        self._event_bus = event_bus
        self._memory = memory
        self._concurrency_limit = concurrency_limit
        self._executor = TaskExecutor(event_bus, memory)

        self._running_tasks: Dict[str, asyncio.Task[Any]] = {}
        self._cancelled: bool = False
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        """
        Sets the cancellation flag to terminate execution in the next cycle.
        """
        self._cancelled = True
        self._cancel_event.set()
        logger.warning("Scheduler cancellation flag set.")

    async def execute_dag(self, dag: TaskDAG) -> Dict[str, Any]:
        """
        Executes the tasks in a Directed Acyclic Graph concurrently.
        Blocks until completion, failure, or cancellation.

        Args:
            dag (TaskDAG): The validated Directed Acyclic Graph.

        Returns:
            Dict[str, Any]: A dictionary mapping task IDs to task execution results.
        """
        self._cancelled = False
        self._cancel_event.clear()
        self._running_tasks.clear()
        tasks = dag.tasks

        # Ensure all tasks start as PENDING
        for task in tasks.values():
            if task.state != TaskState.PENDING:
                task.update_state(TaskState.PENDING)

        logger.info(f"Starting execution of DAG with {len(tasks)} tasks.")

        while True:
            # 1. Update task states: check dependencies
            for task_id, task in list(tasks.items()):
                if task.state == TaskState.PENDING:
                    # Check if all dependencies completed successfully
                    deps_completed = all(
                        tasks[dep_id].state == TaskState.COMPLETED
                        for dep_id in task.dependencies
                    )
                    # Check if any dependency failed, cancelled, or was skipped
                    dep_failed_or_skipped = any(
                        tasks[dep_id].state
                        in (TaskState.FAILED, TaskState.CANCELLED, TaskState.SKIPPED)
                        for dep_id in task.dependencies
                    )

                    if dep_failed_or_skipped:
                        self._cascade_skip(task, tasks)
                    elif deps_completed:
                        task.update_state(TaskState.READY)
                        self._publish_event("task.ready", task)
                        logger.debug(f"Task '{task.id}' [{task.name}] is READY.")

            # 2. Check if cancelled and abort
            if self._cancelled:
                logger.warning(
                    "Scheduler processing cancellation. Aborting running tasks..."
                )
                # Cancel running tasks
                for tid, fut in list(self._running_tasks.items()):
                    if not fut.done():
                        fut.cancel()

                if self._running_tasks:
                    await asyncio.gather(
                        *self._running_tasks.values(), return_exceptions=True
                    )

                # Transition all remaining uncompleted tasks to CANCELLED
                for task in tasks.values():
                    if task.state in (
                        TaskState.PENDING,
                        TaskState.READY,
                        TaskState.RUNNING,
                        TaskState.RETRYING,
                    ):
                        task.update_state(TaskState.CANCELLED)
                        self._publish_event("task.cancelled", task)

                break

            # 3. Check if all tasks finished
            all_finished = all(
                task.state
                in (
                    TaskState.COMPLETED,
                    TaskState.FAILED,
                    TaskState.CANCELLED,
                    TaskState.SKIPPED,
                )
                for task in tasks.values()
            )
            if all_finished:
                logger.info("All tasks in the DAG have finished execution.")
                break

            # 4. Launch ready tasks up to available slots
            ready_tasks = [t for t in tasks.values() if t.state == TaskState.READY]
            available_slots = self._concurrency_limit - len(self._running_tasks)

            for task in ready_tasks[:available_slots]:
                task.update_state(
                    TaskState.RUNNING
                )  # Instantly set state to avoid duplicate launching
                task_id = task.id
                # Dispatch execution asynchronously
                fut = asyncio.create_task(self._executor.execute(task))
                self._running_tasks[task_id] = fut

            # 5. Wait for at least one running task to complete or cancellation
            if self._running_tasks:
                cancel_wait_task = asyncio.create_task(self._cancel_event.wait())

                done, _ = await asyncio.wait(
                    list(self._running_tasks.values()) + [cancel_wait_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if cancel_wait_task in done:
                    # Cancelled, loop will abort in next cycle
                    pass
                else:
                    cancel_wait_task.cancel()

                # Clean completed tasks from tracking dict
                for completed_fut in done:
                    if completed_fut is cancel_wait_task:
                        continue
                    completed_tid = None
                    for tid, running_fut in self._running_tasks.items():
                        if running_fut is completed_fut:
                            completed_tid = tid
                            break
                    if completed_tid:
                        del self._running_tasks[completed_tid]
            else:
                # No tasks running and none are ready, but not all finished.
                # Avoid deadlock due to incomplete dependency configurations.
                logger.warning(
                    "No tasks are running and none are ready. Aborting execution loop."
                )
                break

        # Check for failed tasks and raise the first error to propagate failures up
        failed_tasks = [t for t in tasks.values() if t.state == TaskState.FAILED]
        if failed_tasks:
            first_error = failed_tasks[0].error
            if first_error:
                raise first_error
            raise RuntimeError("DAG execution failed due to task failures.")

        # Return results mapping
        return {tid: task.result for tid, task in tasks.items()}

    def _cascade_skip(self, task: Task, all_tasks: Dict[str, Task]) -> None:
        """
        Recursively transitions the task and all downstream descendants to SKIPPED.
        """
        if task.state == TaskState.SKIPPED:
            return

        task.update_state(TaskState.SKIPPED)
        self._publish_event("task.skipped", task)
        logger.info(
            f"Cascading skip on task '{task.id}' [{task.name}] due to dependency failure."
        )

        # Recursively skip dependents depending on this task
        for dependent in all_tasks.values():
            if (
                task.id in dependent.dependencies
                and dependent.state != TaskState.SKIPPED
            ):
                self._cascade_skip(dependent, all_tasks)

    def _publish_event(self, event_type: str, task: Task) -> None:
        """Helper to publish an event on the event bus."""
        event = Event(
            event_type=event_type,
            metadata={"task_id": task.id},
            data={
                "task_id": task.id,
                "name": task.name,
                "state": task.state,
                "progress": task.progress,
            },
        )
        self._event_bus.publish(event)
