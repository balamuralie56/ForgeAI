"""
Tests for cancelling workflow runs interrupted by a server stop
(forge_api/recovery.py), at unit level and through the API's startup.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from forge_api import bootstrap, recovery, runner
from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.service import ConfigurationService
from forge_core.event_bus.event_bus import ForgeAIEventBus
from forge_core.event_bus.service import EventBusService
from forge_core.history.service import ForgeAIHistoryService, HistoryService
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.memory.service import ForgeAIMemoryService, MemoryService
from forge_core.workflow.models import Workflow, WorkflowState, WorkflowType
from forge_core.workflow.service import ForgeAIWorkflowService, WorkflowService
from forge_plugins.planner.service import PlannerService


class TestCancelInterruptedRuns(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        tmp = Path(self.temp_dir.name)
        defaults = json.loads(Path("config/defaults.json").read_text(encoding="utf-8"))
        defaults["system"]["workspace_dir"] = str(tmp).replace("\\", "/")
        (tmp / "defaults.json").write_text(json.dumps(defaults), encoding="utf-8")

        registry = ServiceRegistry()
        registry.register(
            ConfigurationService,  # type: ignore[type-abstract]
            ConfigurationManager(
                config_path="forge.json", defaults_path=str(tmp / "defaults.json")
            ),
        )
        self.event_bus = ForgeAIEventBus()
        self.event_bus.initialize()
        registry.register(EventBusService, self.event_bus)  # type: ignore[type-abstract]
        self.memory = ForgeAIMemoryService(db_path=str(tmp / "memory.db"))
        self.memory.initialize()
        registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
        self.history = ForgeAIHistoryService(str(tmp / "history.db"))
        self.history.initialize()
        registry.register(HistoryService, self.history)  # type: ignore[type-abstract]
        registry.register(PlannerService, MagicMock(spec=PlannerService))
        self.workflows = ForgeAIWorkflowService(registry)
        self.workflows.initialize()

    def tearDown(self) -> None:
        self.workflows.shutdown()
        self.history.shutdown()
        self.memory.shutdown()
        self.event_bus.shutdown()
        self.temp_dir.cleanup()

    def _workflow(self, state: WorkflowState) -> Workflow:
        workflow = self.workflows.create_workflow(
            WorkflowType.BUILD_ONLY, "run", "goal"
        )
        if state is not WorkflowState.PENDING:
            workflow.state = state
            workflow.stages[0].status = WorkflowState.COMPLETED
            workflow.stages[1].status = (
                WorkflowState.RUNNING if state is WorkflowState.RUNNING else state
            )
            assert self.workflows._orchestrator is not None
            self.workflows._orchestrator._save_workflow(workflow)
        return workflow

    def _history_state(self, workflow_id: str) -> str:
        run = self.history.get_run(workflow_id)
        assert run is not None
        return run.summary.state

    def test_active_runs_are_cancelled_and_finished_runs_left_alone(self) -> None:
        running = self._workflow(WorkflowState.RUNNING)
        pending = self._workflow(WorkflowState.PENDING)
        completed = self._workflow(WorkflowState.COMPLETED)
        failed = self._workflow(WorkflowState.FAILED)

        cancelled = recovery.cancel_interrupted_runs(self.history, self.workflows)

        self.assertCountEqual(cancelled, [running.id, pending.id])
        self.assertEqual(self._history_state(running.id), "CANCELLED")
        self.assertEqual(self._history_state(pending.id), "CANCELLED")
        self.assertEqual(self._history_state(completed.id), "COMPLETED")
        self.assertEqual(self._history_state(failed.id), "FAILED")

    def test_interrupted_stage_and_reason_are_recorded(self) -> None:
        running = self._workflow(WorkflowState.RUNNING)

        recovery.cancel_interrupted_runs(self.history, self.workflows)

        loaded = self.workflows.load_workflow(running.id)
        assert loaded is not None
        self.assertEqual(loaded.state, WorkflowState.CANCELLED)
        self.assertEqual(loaded.stages[0].status, WorkflowState.COMPLETED)
        self.assertEqual(loaded.stages[1].status, WorkflowState.CANCELLED)
        self.assertEqual(loaded.stages[1].error, recovery.INTERRUPTED_MESSAGE)
        self.assertEqual(loaded.stages[2].status, WorkflowState.PENDING)
        self.assertEqual(loaded.errors["interrupted"], recovery.INTERRUPTED_MESSAGE)

        run = self.history.get_run(running.id)
        assert run is not None
        self.assertEqual(run.errors["interrupted"], recovery.INTERRUPTED_MESSAGE)
        self.assertEqual(run.stages[1]["status"], "CANCELLED")

    def test_is_idempotent(self) -> None:
        self._workflow(WorkflowState.RUNNING)
        recovery.cancel_interrupted_runs(self.history, self.workflows)
        self.assertEqual(
            recovery.cancel_interrupted_runs(self.history, self.workflows), []
        )

    def test_run_without_saved_workflow_state_is_skipped(self) -> None:
        self.history.record_run_snapshot({"id": "orphan", "state": "RUNNING"}, "m")

        cancelled = recovery.cancel_interrupted_runs(self.history, self.workflows)

        self.assertEqual(cancelled, [])
        self.assertEqual(self._history_state("orphan"), "RUNNING")

    def test_cancel_failure_is_logged_and_other_runs_continue(self) -> None:
        first = self._workflow(WorkflowState.RUNNING)
        second = self._workflow(WorkflowState.RUNNING)
        real_cancel = self.workflows.cancel_workflow

        def cancel(workflow: Workflow) -> None:
            if workflow.id == first.id:
                from forge_core.workflow.exceptions import WorkflowStateError

                raise WorkflowStateError("boom")
            real_cancel(workflow)

        with patch.object(self.workflows, "cancel_workflow", side_effect=cancel):
            cancelled = recovery.cancel_interrupted_runs(self.history, self.workflows)

        self.assertEqual(cancelled, [second.id])

    def test_scans_every_page_of_history(self) -> None:
        ids = [self._workflow(WorkflowState.RUNNING).id for _ in range(5)]
        with patch.object(recovery, "_PAGE_SIZE", 2):
            cancelled = recovery.cancel_interrupted_runs(self.history, self.workflows)
        self.assertCountEqual(cancelled, ids)


class TestRecoveryOnApiStartup(unittest.TestCase):
    """The API cancels interrupted runs as it starts, before any new run can begin."""

    def setUp(self) -> None:
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        shutil.copytree(
            Path(self.original_cwd) / "config", Path(self.temp_dir.name) / "config"
        )
        shutil.copytree(
            Path(self.original_cwd) / "forge_plugins",
            Path(self.temp_dir.name) / "forge_plugins",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        os.chdir(self.temp_dir.name)
        self.kernel = ForgeAIKernel(
            config_path="forge.json", defaults_path="config/defaults.json"
        )
        self.kernel.boot()
        bootstrap._kernel = self.kernel
        runner._active_workflow_id = None

    def tearDown(self) -> None:
        bootstrap.shutdown_kernel()
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def test_startup_cancels_a_run_left_running(self) -> None:
        workflows = self.kernel.registry.resolve(WorkflowService)  # type: ignore[type-abstract]
        workflow = workflows.create_workflow(WorkflowType.BUILD_ONLY, "left", "goal")
        workflow.state = WorkflowState.RUNNING
        workflow.stages[0].status = WorkflowState.RUNNING
        workflows._orchestrator._save_workflow(workflow)  # type: ignore[attr-defined]

        from forge_api.main import app

        with TestClient(app) as client:
            run = client.get(f"/api/history/runs/{workflow.id}").json()
            status = client.get(f"/api/workflows/{workflow.id}").json()

        self.assertEqual(run["state"], "CANCELLED")
        self.assertIn("interrupted", run["errors"])
        self.assertEqual(status["state"], "CANCELLED")
        self.assertEqual(status["stages"][0]["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
