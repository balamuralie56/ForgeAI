"""
Directed Acyclic Graph (DAG) structures and validation for the Task Engine.
Ensures cycle detection and dependency resolution.
"""

from typing import Dict, List, Set

from .models import Task


class DAGValidationError(ValueError):
    """
    Raised when a DAG structure is invalid (e.g., contains cycles or missing nodes).
    """

    pass


class TaskDAG:
    """
    Directed Acyclic Graph containing Tasks.
    Performs structural validation upon initialization.
    """

    def __init__(self, tasks: List[Task]) -> None:
        """
        Initializes the TaskDAG and validates its structure.

        Args:
            tasks (List[Task]): The nodes to form the DAG.

        Raises:
            DAGValidationError: If dependencies are missing or circular.
        """
        self.tasks: Dict[str, Task] = {t.id: t for t in tasks}
        self.validate()

    def validate(self) -> None:
        """
        Validates the DAG:
        1. Checks that all referenced dependencies exist.
        2. Detects cycle paths using DFS coloring algorithm.

        Raises:
            DAGValidationError: If validation fails.
        """
        # 1. Dependency exists check
        for task_id, task in self.tasks.items():
            for dep in task.dependencies:
                if dep not in self.tasks:
                    raise DAGValidationError(
                        f"Task '{task_id}' depends on '{dep}' which is not in the DAG."
                    )

        # 2. Cycle detection (DFS coloring: 0=unvisited, 1=visiting, 2=visited)
        state: Dict[str, int] = {tid: 0 for tid in self.tasks}

        def visit(node_id: str) -> None:
            state[node_id] = 1  # visiting
            for dep in self.tasks[node_id].dependencies:
                if state[dep] == 1:
                    raise DAGValidationError(
                        f"Circular dependency cycle detected: '{node_id}' -> '{dep}'."
                    )
                elif state[dep] == 0:
                    visit(dep)
            state[node_id] = 2  # visited

        for task_id in self.tasks:
            if state[task_id] == 0:
                visit(task_id)

    def get_topological_sort(self) -> List[str]:
        """
        Computes a topological sort order where dependencies precede dependent tasks.

        Returns:
            List[str]: List of task IDs in execution order.
        """
        visited: Set[str] = set()
        order: List[str] = []

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            for dep in self.tasks[node_id].dependencies:
                visit(dep)
            visited.add(node_id)
            order.append(node_id)

        for task_id in self.tasks:
            visit(task_id)
        return order
