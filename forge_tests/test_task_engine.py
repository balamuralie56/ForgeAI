"""
Unit, integration, and concurrency tests for the ForgeAI Task Engine.
"""

import asyncio
import unittest
from typing import Dict, List, Any

from forge_core.event_bus import ForgeAIEventBus, Event
from forge_core.memory import ForgeAIMemoryService
from forge_core.task_engine import (
    ForgeAITaskEngine,
    Task,
    TaskDAG,
    TaskState,
    RetryPolicy,
    DAGValidationError,
)


class TestTaskEngine(unittest.TestCase):
    """Test suite verifying Task DAG execution flow, retries, concurrency, and failures."""

    def setUp(self) -> None:
        """Sets up isolated engines for each test run."""
        self.event_bus = ForgeAIEventBus()
        self.event_bus.initialize()

        # In-memory database path for memory isolation in testing
        self.memory = ForgeAIMemoryService(db_path=":memory:")
        self.memory.initialize()

        self.task_engine = ForgeAITaskEngine(
            event_bus=self.event_bus, memory=self.memory, concurrency_limit=3
        )
        self.task_engine.initialize()

        self.events_received: List[Event] = []
        self.event_bus.subscribe("*", lambda e: self.events_received.append(e))

    def tearDown(self) -> None:
        """Gracefully shuts down testing engines."""
        self.task_engine.shutdown()
        self.memory.shutdown()
        self.event_bus.shutdown()

    def test_dag_validation_cycle_detection(self) -> None:
        """Tests that circular task dependencies raise DAGValidationError."""
        task_a = Task("A", "Task A", lambda: None, dependencies=["B"])
        task_b = Task("B", "Task B", lambda: None, dependencies=["A"])

        with self.assertRaises(DAGValidationError):
            TaskDAG([task_a, task_b])

    def test_dag_validation_missing_dependency(self) -> None:
        """Tests that missing dependency nodes raise DAGValidationError."""
        task_a = Task("A", "Task A", lambda: None, dependencies=["C"])

        with self.assertRaises(DAGValidationError):
            TaskDAG([task_a])

    def test_successful_dag_execution(self) -> None:
        """Tests executing a linear sequence of successful tasks."""
        results: Dict[str, Any] = {}

        def make_action(name: str, val: int) -> Any:
            def action() -> int:
                results[name] = val
                return val

            return action

        task_1 = Task("1", "T1", make_action("T1", 10))
        task_2 = Task("2", "T2", make_action("T2", 20), dependencies=["1"])

        dag = TaskDAG([task_1, task_2])
        run_id = self.task_engine.submit_dag(dag)

        run_results = asyncio.run(self.task_engine.execute_dag(run_id))

        self.assertEqual(run_results["1"], 10)
        self.assertEqual(run_results["2"], 20)
        self.assertEqual(results["T1"], 10)
        self.assertEqual(results["T2"], 20)

        self.assertEqual(task_1.state, TaskState.COMPLETED)
        self.assertEqual(task_2.state, TaskState.COMPLETED)

        # Verify event bus notifications
        event_types = [e.event_type for e in self.events_received]
        self.assertIn("task.started", event_types)
        self.assertIn("task.completed", event_types)

        # Verify completed task memory recording
        completed_records = self.memory.project.get_completed_tasks()
        self.assertIn("1", completed_records)
        self.assertIn("2", completed_records)
        self.assertEqual(completed_records["1"]["result"], 10)

    def test_task_timeout(self) -> None:
        """Tests that a task timing out transitions to FAILED state."""

        async def slow_action() -> None:
            await asyncio.sleep(0.5)

        task = Task("slow", "Slow Task", slow_action, timeout=0.1)
        dag = TaskDAG([task])
        run_id = self.task_engine.submit_dag(dag)

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(self.task_engine.execute_dag(run_id))

        self.assertEqual(task.state, TaskState.FAILED)
        self.assertIsInstance(task.error, asyncio.TimeoutError)

    def test_retry_policy_with_exponential_backoff(self) -> None:
        """Tests that failing tasks are retried with backoff and succeed if errors resolve."""
        attempts = 0

        def flaking_callable() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("Temporary flaking error")
            return "recovered"

        policy = RetryPolicy(
            max_retries=2, initial_delay=0.01, backoff_factor=2.0, jitter=False
        )
        task = Task("flake", "Flaking Task", flaking_callable, retry_policy=policy)

        dag = TaskDAG([task])
        run_id = self.task_engine.submit_dag(dag)

        results = asyncio.run(self.task_engine.execute_dag(run_id))

        self.assertEqual(results["flake"], "recovered")
        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(attempts, 3)

        # Verify retry events are dispatched
        event_types = [e.event_type for e in self.events_received]
        self.assertIn("task.retrying", event_types)

    def test_failure_cascading_skips_children(self) -> None:
        """Tests that downstream tasks are skipped when a root dependency fails."""

        def failing_action() -> None:
            raise RuntimeError("Fatal error")

        task_fail = Task("fail", "Failing Task", failing_action)
        task_skip = Task("skip", "Dependent Task", lambda: None, dependencies=["fail"])

        dag = TaskDAG([task_fail, task_skip])
        run_id = self.task_engine.submit_dag(dag)

        with self.assertRaises(RuntimeError):
            asyncio.run(self.task_engine.execute_dag(run_id))

        self.assertEqual(task_fail.state, TaskState.FAILED)
        self.assertEqual(task_skip.state, TaskState.SKIPPED)

        # Verify event bus recorded the skip
        event_types = [e.event_type for e in self.events_received]
        self.assertIn("task.skipped", event_types)

    def test_concurrency_execution(self) -> None:
        """Tests concurrent task execution respects dependency execution order."""
        seq: List[str] = []

        async def action_sleep(task_id: str, delay: float) -> str:
            await asyncio.sleep(delay)
            seq.append(task_id)
            return task_id

        task_a = Task("A", "Task A", lambda: action_sleep("A", 0.05))
        task_b = Task("B", "Task B", lambda: action_sleep("B", 0.01))
        task_c = Task(
            "C", "Task C", lambda: action_sleep("C", 0.01), dependencies=["A", "B"]
        )

        dag = TaskDAG([task_a, task_b, task_c])
        run_id = self.task_engine.submit_dag(dag)

        # Execution starts A and B concurrently.
        # B will finish before A since B has 0.01s sleep vs 0.05s sleep.
        # C will start only after A and B complete.
        asyncio.run(self.task_engine.execute_dag(run_id))

        self.assertEqual(seq[0], "B")
        self.assertEqual(seq[1], "A")
        self.assertEqual(seq[2], "C")


if __name__ == "__main__":
    unittest.main()
