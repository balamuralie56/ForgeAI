"""
Unit tests for WorkflowStageScheduler - retry policy, timeout enforcement, and events.
"""

import time
import unittest
from unittest.mock import MagicMock

from forge_core.event_bus.service import EventBusService
from forge_core.workflow.exceptions import WorkflowStageError
from forge_core.workflow.models import (
    Workflow,
    WorkflowStage,
    WorkflowState,
    WorkflowType,
)
from forge_core.workflow.scheduler import WorkflowStageScheduler


class _DummyService:
    """Placeholder service_interface - the scheduler never touches this field."""


class TestWorkflowStageScheduler(unittest.TestCase):
    """Test suite for stage execution timeout and retry behaviour."""

    def setUp(self) -> None:
        self.mock_event_bus = MagicMock(spec=EventBusService)
        self.scheduler = WorkflowStageScheduler(self.mock_event_bus)
        self.workflow = Workflow(
            id="wf-1",
            name="test",
            type=WorkflowType.FULL_ENGINEERING,
            state=WorkflowState.RUNNING,
            stages=[],
        )

    def _make_stage(self, **overrides: object) -> WorkflowStage:
        defaults: dict = dict(
            name="developer",
            service_interface=_DummyService,
            method_name="run",
            retry_count=1,
            retry_delay=0.01,
            timeout=5.0,
        )
        defaults.update(overrides)
        return WorkflowStage(**defaults)  # type: ignore[arg-type]

    def test_execute_stage_returns_result_on_success(self) -> None:
        stage = self._make_stage(name="planner", retry_count=1, timeout=5.0)
        result = self.scheduler.execute_stage(self.workflow, stage, lambda: "done")

        self.assertEqual(result, "done")
        self.assertEqual(stage.status, WorkflowState.COMPLETED)

    def test_timeout_raises_and_returns_promptly(self) -> None:
        """
        A slow, non-cooperative action (no cancellation checks - the same shape
        as a blocking LLM HTTP call) must not stall the caller past the
        configured timeout. Regression test for the executor-as-context-manager
        bug where `shutdown(wait=True)` on __exit__ silently re-blocked until
        the orphaned thread finished, so a stage "timeout" never actually
        bounded wall-clock time.
        """
        stage = self._make_stage(retry_count=0, timeout=0.2)

        def slow_action() -> str:
            time.sleep(2.0)
            return "too late"

        started = time.monotonic()
        with self.assertRaises(WorkflowStageError):
            self.scheduler.execute_stage(self.workflow, stage, slow_action)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        self.assertEqual(stage.status, WorkflowState.FAILED)

    def test_retries_then_succeeds(self) -> None:
        stage = self._make_stage(retry_count=2, timeout=5.0)
        calls = {"count": 0}

        def flaky_action() -> str:
            calls["count"] += 1
            if calls["count"] < 3:
                raise ValueError("transient")
            return "ok"

        result = self.scheduler.execute_stage(self.workflow, stage, flaky_action)

        self.assertEqual(result, "ok")
        self.assertEqual(calls["count"], 3)

    def test_exhausts_retries_and_raises_workflow_stage_error(self) -> None:
        stage = self._make_stage(retry_count=1, timeout=5.0)

        def always_fails() -> str:
            raise ValueError("permanent failure")

        with self.assertRaises(WorkflowStageError) as ctx:
            self.scheduler.execute_stage(self.workflow, stage, always_fails)

        self.assertIn("permanent failure", str(ctx.exception))
        self.assertEqual(stage.status, WorkflowState.FAILED)
        self.assertIsNotNone(stage.error)


if __name__ == "__main__":
    unittest.main()
