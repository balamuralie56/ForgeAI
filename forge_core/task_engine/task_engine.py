"""
Concrete implementation of the ForgeAI Task Engine orchestrator.
Manages submission, retrieval, cancellation, and execution of TaskDAG pipelines.
"""

import logging
import uuid
from typing import Dict, Any, Optional

from forge_core.kernel.lifecycle import LifecycleComponent
from forge_core.event_bus.interface import EventBus
from forge_core.memory.service import MemoryService
from .service import TaskEngineService
from .models import TaskState
from .dag import TaskDAG
from .scheduler import TaskScheduler

logger = logging.getLogger("ForgeAI.TaskEngine")


class ForgeAITaskEngine(TaskEngineService, LifecycleComponent):
    """
    Concrete Task Engine.
    Coordinates submitted DAG tasks and executes them asynchronously.
    """

    def __init__(
        self, event_bus: EventBus, memory: MemoryService, concurrency_limit: int = 5
    ) -> None:
        """
        Initializes the Task Engine with system services.

        Args:
            event_bus (EventBus): Central Event Bus.
            memory (MemoryService): Central Memory Engine.
            concurrency_limit (int): Max concurrent execution tasks.
        """
        self._event_bus = event_bus
        self._memory = memory
        self._concurrency_limit = concurrency_limit

        self._dag_runs: Dict[str, TaskDAG] = {}
        self._schedulers: Dict[str, TaskScheduler] = {}

    def initialize(self) -> None:
        """Initializes the Task Engine (lifecycle hook)."""
        logger.info("Task Engine service initialized.")

    def shutdown(self) -> None:
        """Shuts down the Task Engine, cancelling all active runs (lifecycle hook)."""
        logger.info("Task Engine shutting down. Cancelling all running DAGs...")
        for scheduler in list(self._schedulers.values()):
            scheduler.cancel()
        self._schedulers.clear()
        self._dag_runs.clear()
        logger.info("Task Engine shutdown complete.")

    def submit_dag(self, dag: Any, dag_id: Optional[str] = None) -> str:
        """
        Registers a validated TaskDAG under a unique execution run ID.

        Args:
            dag (TaskDAG): The validated Directed Acyclic Graph container.
            dag_id (Optional[str]): A custom ID, if desired.

        Returns:
            str: A unique run ID.
        """
        if not isinstance(dag, TaskDAG):
            raise TypeError("Submitted graph must be an instance of TaskDAG.")

        run_id = dag_id or str(uuid.uuid4())
        self._dag_runs[run_id] = dag

        # Log to runtime memory
        self._memory.runtime.set_execution_state(f"dag:{run_id}:status", "SUBMITTED")
        logger.info(
            f"DAG '{run_id}' submitted successfully with {len(dag.tasks)} tasks."
        )
        return run_id

    async def execute_dag(self, dag_id: str) -> Dict[str, Any]:
        """
        Executes a submitted DAG by its identifier.

        Args:
            dag_id (str): Unique identifier of the submitted DAG.

        Returns:
            Dict[str, Any]: Mapping of task ID to task result.

        Raises:
            KeyError: If the DAG run ID is not found.
        """
        if dag_id not in self._dag_runs:
            raise KeyError(f"No DAG found with identifier: '{dag_id}'")

        dag = self._dag_runs[dag_id]
        scheduler = TaskScheduler(
            event_bus=self._event_bus,
            memory=self._memory,
            concurrency_limit=self._concurrency_limit,
        )

        self._schedulers[dag_id] = scheduler
        self._memory.runtime.set_execution_state(f"dag:{dag_id}:status", "RUNNING")

        try:
            results = await scheduler.execute_dag(dag)

            # Determine final overall status
            final_status = "COMPLETED"
            for task in dag.tasks.values():
                if task.state == TaskState.FAILED:
                    final_status = "FAILED"
                    break
                elif task.state == TaskState.CANCELLED:
                    final_status = "CANCELLED"
                    break

            self._memory.runtime.set_execution_state(
                f"dag:{dag_id}:status", final_status
            )
            logger.info(
                f"DAG '{dag_id}' finished execution with status: {final_status}."
            )
            return results

        finally:
            if dag_id in self._schedulers:
                del self._schedulers[dag_id]

    def get_dag_state(self, dag_id: str) -> Dict[str, TaskState]:
        """
        Queries states of tasks in the active DAG run.

        Args:
            dag_id (str): DAG run identifier.

        Returns:
            Dict[str, TaskState]: Mapping of task ID to TaskState.
        """
        if dag_id not in self._dag_runs:
            raise KeyError(f"No DAG found with identifier: '{dag_id}'")

        dag = self._dag_runs[dag_id]
        return {tid: task.state for tid, task in dag.tasks.items()}

    def cancel_dag(self, dag_id: str) -> None:
        """
        Requests cancellation of an active DAG run.

        Args:
            dag_id (str): DAG run identifier.
        """
        if dag_id in self._schedulers:
            self._schedulers[dag_id].cancel()
            logger.info(f"Requested cancellation for running DAG '{dag_id}'.")
        else:
            logger.warning(f"No active scheduler found for DAG '{dag_id}' to cancel.")
