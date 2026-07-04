"""
Interface definitions for the ForgeAI Task Engine.
Defines the client-facing orchestrator contract for DAG submission and execution.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .models import TaskState


class TaskEngine(ABC):
    """
    Standard interface representing the Task Engine subsystem.
    Orchestrates DAG execution, tracking, cancellation, and state persistence.
    """

    @abstractmethod
    def submit_dag(self, dag: Any, dag_id: Optional[str] = None) -> str:
        """
        Submits a Directed Acyclic Graph (DAG) for execution.

        Args:
            dag (TaskDAG): The validated DAG container.
            dag_id (Optional[str]): A unique ID. Generated if not supplied.

        Returns:
            str: The unique ID identifying this execution run.
        """
        pass

    @abstractmethod
    async def execute_dag(self, dag_id: str) -> Dict[str, Any]:
        """
        Triggers execution of the submitted DAG.
        Runs independent tasks concurrently and tracks their dependency state.

        Args:
            dag_id (str): The unique ID of the DAG to execute.

        Returns:
            Dict[str, Any]: A map of task ID to task result.
        """
        pass

    @abstractmethod
    def get_dag_state(self, dag_id: str) -> Dict[str, TaskState]:
        """
        Retrieves the current execution states of all tasks in the DAG.

        Args:
            dag_id (str): The unique ID of the DAG.

        Returns:
            Dict[str, TaskState]: Dictionary mapping task IDs to TaskStates.
        """
        pass

    @abstractmethod
    def cancel_dag(self, dag_id: str) -> None:
        """
        Terminates a running DAG execution and transitions running/pending tasks.

        Args:
            dag_id (str): The unique ID of the DAG.
        """
        pass
