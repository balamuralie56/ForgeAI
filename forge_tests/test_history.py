"""
Unit, failure, concurrency, and orchestrator-integration tests for the
ForgeAI History Engine.
"""

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.service import ConfigurationService
from forge_core.event_bus.event_bus import ForgeAIEventBus
from forge_core.event_bus.service import EventBusService
from forge_core.history import (
    ForgeAIHistoryService,
    HistoryError,
    HistoryService,
    InvalidSnapshotError,
    SQLiteHistoryStore,
)
from forge_core.history.store import SCHEMA_VERSION
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.memory.service import ForgeAIMemoryService, MemoryService
from forge_core.workflow.models import WorkflowType
from forge_core.workflow.service import ForgeAIWorkflowService
from forge_plugins.architect.service import ArchitectService
from forge_plugins.planner.service import PlannerService


def make_snapshot(
    workflow_id: str = "wf-1",
    state: str = "RUNNING",
    created_at: float = 1000.0,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a dict shaped like Workflow.to_dict()."""
    return {
        "id": workflow_id,
        "name": f"run {workflow_id}",
        "type": "BUILD_ONLY",
        "state": state,
        "stages": [{"name": "planner", "status": "COMPLETED"}],
        "current_stage_index": 1,
        "context": context if context is not None else {"goal": "Build a todo app"},
        "errors": {},
        "progress": 33.33,
        "created_at": created_at,
        "updated_at": created_at + 5,
    }


class TestHistoryService(unittest.TestCase):
    """Behaviour of the History Service against an isolated database."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "history.db")
        self.history = ForgeAIHistoryService(self.db_path)
        self.history.initialize()

    def tearDown(self) -> None:
        self.history.shutdown()
        self.temp_dir.cleanup()

    def test_record_creates_run_with_goal_and_model(self) -> None:
        self.history.record_run_snapshot(make_snapshot(), "qwen2.5-coder:3b")

        run = self.history.get_run("wf-1")
        assert run is not None
        self.assertEqual(run.summary.goal, "Build a todo app")
        self.assertEqual(run.summary.model, "qwen2.5-coder:3b")
        self.assertEqual(run.summary.workflow_type, "BUILD_ONLY")
        self.assertEqual(run.summary.created_at, 1000.0)
        self.assertEqual(run.stages, [{"name": "planner", "status": "COMPLETED"}])
        self.assertEqual(run.artifact_kinds, [])

    def test_snapshot_updates_existing_run_and_keeps_creation_time(self) -> None:
        self.history.record_run_snapshot(make_snapshot(state="RUNNING"), "m")
        later = make_snapshot(state="COMPLETED", created_at=1000.0)
        later["updated_at"] = 2000.0
        later["progress"] = 100.0
        self.history.record_run_snapshot(later, "m")

        self.assertEqual(self.history.count_runs(), 1)
        run = self.history.get_run("wf-1")
        assert run is not None
        self.assertEqual(run.summary.state, "COMPLETED")
        self.assertEqual(run.summary.progress, 100.0)
        self.assertEqual(run.summary.created_at, 1000.0)
        self.assertEqual(run.summary.updated_at, 2000.0)

    def test_artifacts_are_stored_per_run_and_not_overwritten_by_other_runs(
        self,
    ) -> None:
        for wf_id, title in (("wf-a", "Plan A"), ("wf-b", "Plan B")):
            ctx = {
                "goal": "g",
                "project_plan": {"goal": {"goal": title}},
                "test_report": {"status": "PASSED"},
                "unrelated_key": {"ignored": True},
            }
            self.history.record_run_snapshot(
                make_snapshot(wf_id, context=ctx, created_at=1.0), "m"
            )

        plan_a = self.history.get_artifact("wf-a", "project_plan")
        plan_b = self.history.get_artifact("wf-b", "project_plan")
        assert plan_a is not None and plan_b is not None
        self.assertEqual(plan_a["goal"]["goal"], "Plan A")
        self.assertEqual(plan_b["goal"]["goal"], "Plan B")

        run = self.history.get_run("wf-a")
        assert run is not None
        self.assertEqual(run.artifact_kinds, ["project_plan", "test_report"])

    def test_non_dict_report_values_are_not_stored(self) -> None:
        ctx = {"goal": "g", "project_plan": "not a dict", "git_report": None}
        self.history.record_run_snapshot(make_snapshot(context=ctx), "m")

        run = self.history.get_run("wf-1")
        assert run is not None
        self.assertEqual(run.artifact_kinds, [])

    def test_unchanged_artifact_is_not_rewritten(self) -> None:
        ctx = {"goal": "g", "project_plan": {"v": 1}}
        self.history.record_run_snapshot(make_snapshot(context=ctx), "m")

        conn = sqlite3.connect(self.db_path)
        before = conn.execute("SELECT updated_at FROM artifacts").fetchone()[0]

        again = make_snapshot(context=ctx)
        again["updated_at"] = 9999.0
        self.history.record_run_snapshot(again, "m")
        after = conn.execute("SELECT updated_at FROM artifacts").fetchone()[0]
        conn.close()
        self.assertEqual(before, after)

        changed = make_snapshot(context={"goal": "g", "project_plan": {"v": 2}})
        changed["updated_at"] = 9999.0
        self.history.record_run_snapshot(changed, "m")
        plan = self.history.get_artifact("wf-1", "project_plan")
        self.assertEqual(plan, {"v": 2})

    def test_list_runs_newest_first_with_pagination(self) -> None:
        for i in range(5):
            self.history.record_run_snapshot(
                make_snapshot(f"wf-{i}", created_at=100.0 + i), "m"
            )

        ids = [r.workflow_id for r in self.history.list_runs(limit=10)]
        self.assertEqual(ids, ["wf-4", "wf-3", "wf-2", "wf-1", "wf-0"])

        page = [r.workflow_id for r in self.history.list_runs(limit=2, offset=1)]
        self.assertEqual(page, ["wf-3", "wf-2"])
        self.assertEqual(self.history.count_runs(), 5)

    def test_missing_lookups_return_none(self) -> None:
        self.assertIsNone(self.history.get_run("nope"))
        self.assertIsNone(self.history.get_artifact("nope", "project_plan"))
        self.history.record_run_snapshot(make_snapshot(), "m")
        self.assertIsNone(self.history.get_artifact("wf-1", "project_plan"))

    def test_delete_run_removes_run_and_artifacts(self) -> None:
        ctx = {"goal": "g", "project_plan": {"v": 1}}
        self.history.record_run_snapshot(make_snapshot("wf-x", context=ctx), "m")
        self.history.record_run_snapshot(make_snapshot("wf-y", context=ctx), "m")

        self.assertTrue(self.history.delete_run("wf-x"))

        self.assertIsNone(self.history.get_run("wf-x"))
        self.assertIsNone(self.history.get_artifact("wf-x", "project_plan"))
        self.assertIsNotNone(self.history.get_artifact("wf-y", "project_plan"))
        self.assertEqual(self.history.count_runs(), 1)

    def test_delete_missing_run_returns_false(self) -> None:
        self.assertFalse(self.history.delete_run("nope"))

    def test_delete_shrinks_database_file(self) -> None:
        big = {"goal": "g", "implementation_report": {"blob": "x" * 400_000}}
        self.history.record_run_snapshot(make_snapshot("wf-big", context=big), "m")
        size_with_run = self.history.storage_usage().database_bytes

        self.history.delete_run("wf-big")

        self.assertLess(self.history.storage_usage().database_bytes, size_with_run)

    def test_storage_usage_reports_bytes_per_run(self) -> None:
        ctx = {"goal": "g", "project_plan": {"a": 1}}
        self.history.record_run_snapshot(make_snapshot("wf-1", context=ctx), "m")
        self.history.record_run_snapshot(make_snapshot("wf-2"), "m")

        usage = self.history.storage_usage()

        self.assertEqual(usage.run_count, 2)
        self.assertGreater(usage.database_bytes, 0)
        self.assertEqual(
            usage.artifact_bytes_by_run["wf-1"], len(json.dumps({"a": 1}).encode())
        )
        self.assertNotIn("wf-2", usage.artifact_bytes_by_run)

    def test_data_survives_reopening_the_database(self) -> None:
        self.history.record_run_snapshot(make_snapshot(), "m")
        self.history.shutdown()

        reopened = ForgeAIHistoryService(self.db_path)
        reopened.initialize()
        try:
            self.assertIsNotNone(reopened.get_run("wf-1"))
        finally:
            reopened.shutdown()
            self.history = ForgeAIHistoryService(self.db_path)
            self.history.initialize()

    def test_limit_and_offset_are_clamped(self) -> None:
        self.history.record_run_snapshot(make_snapshot(), "m")
        self.assertEqual(len(self.history.list_runs(limit=0, offset=-5)), 1)


class TestHistoryFailures(unittest.TestCase):
    """Failure and edge-case handling."""

    def setUp(self) -> None:
        self.history = ForgeAIHistoryService(":memory:")
        self.history.initialize()

    def tearDown(self) -> None:
        self.history.shutdown()

    def test_snapshot_without_id_is_rejected(self) -> None:
        bad = make_snapshot()
        del bad["id"]
        with self.assertRaises(InvalidSnapshotError):
            self.history.record_run_snapshot(bad, "m")

    def test_snapshot_with_empty_id_is_rejected(self) -> None:
        with self.assertRaises(InvalidSnapshotError):
            self.history.record_run_snapshot(make_snapshot(workflow_id=""), "m")

    def test_non_dict_snapshot_is_rejected(self) -> None:
        with self.assertRaises(InvalidSnapshotError):
            self.history.record_run_snapshot("garbage", "m")  # type: ignore[arg-type]

    def test_snapshot_with_missing_optional_fields_still_records(self) -> None:
        self.history.record_run_snapshot({"id": "bare"}, "m")

        run = self.history.get_run("bare")
        assert run is not None
        self.assertEqual(run.summary.goal, "")
        self.assertEqual(run.summary.progress, 0.0)
        self.assertEqual(run.stages, [])

    def test_use_after_shutdown_raises_history_error(self) -> None:
        self.history.shutdown()
        with self.assertRaises(HistoryError):
            self.history.list_runs()

    def test_database_from_newer_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "future.db")
            conn = sqlite3.connect(path)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            conn.commit()
            conn.close()

            store = SQLiteHistoryStore(path)
            with self.assertRaises(HistoryError):
                store.initialize()

    def test_unwritable_location_raises_history_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "a_file"
            blocker.write_text("x")
            store = SQLiteHistoryStore(str(blocker / "sub" / "h.db"))
            with self.assertRaises((HistoryError, OSError)):
                store.initialize()


class TestHistoryConcurrency(unittest.TestCase):
    """The workflow thread writes while API threads read."""

    def test_concurrent_writers_and_readers(self) -> None:
        history = ForgeAIHistoryService(":memory:")
        history.initialize()
        errors: list[BaseException] = []

        def writer(n: int) -> None:
            try:
                for i in range(25):
                    history.record_run_snapshot(
                        make_snapshot(
                            f"wf-{n}",
                            context={"goal": "g", "project_plan": {"i": i}},
                            created_at=float(n),
                        ),
                        "m",
                    )
            except BaseException as e:  # noqa: BLE001 - surfaced via assertion below
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(50):
                    history.list_runs()
                    history.storage_usage()
            except BaseException as e:  # noqa: BLE001 - surfaced via assertion below
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        try:
            self.assertEqual(errors, [])
            self.assertEqual(history.count_runs(), 4)
            for n in range(4):
                self.assertEqual(
                    history.get_artifact(f"wf-{n}", "project_plan"), {"i": 24}
                )
        finally:
            history.shutdown()


def make_report_mock(data: Dict[str, Any]) -> MagicMock:
    mock = MagicMock()
    mock.to_dict.return_value = data
    return mock


class TestOrchestratorRecordsHistory(unittest.TestCase):
    """A real workflow run lands in history through the orchestrator."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        tmp = Path(self.temp_dir.name)

        defaults = json.loads(Path("config/defaults.json").read_text(encoding="utf-8"))
        defaults["system"]["workspace_dir"] = str(tmp).replace("\\", "/")
        (tmp / "defaults.json").write_text(json.dumps(defaults), encoding="utf-8")

        self.registry = ServiceRegistry()
        self.registry.register(
            ConfigurationService,  # type: ignore[type-abstract]
            ConfigurationManager(
                config_path="forge.json", defaults_path=str(tmp / "defaults.json")
            ),
        )
        self.event_bus = ForgeAIEventBus()
        self.event_bus.initialize()
        self.registry.register(EventBusService, self.event_bus)  # type: ignore[type-abstract]
        self.memory = ForgeAIMemoryService(db_path=str(tmp / "project_memory.db"))
        self.memory.initialize()
        self.registry.register(MemoryService, self.memory)  # type: ignore[type-abstract]
        self.history = ForgeAIHistoryService(str(tmp / "history.db"))
        self.history.initialize()
        self.registry.register(HistoryService, self.history)  # type: ignore[type-abstract]

        self.planner = MagicMock(spec=PlannerService)
        self.architect = MagicMock(spec=ArchitectService)
        self.registry.register(PlannerService, self.planner)
        self.registry.register(ArchitectService, self.architect)

        self.workflow_service = ForgeAIWorkflowService(self.registry)
        self.workflow_service.initialize()

    def tearDown(self) -> None:
        self.workflow_service.shutdown()
        self.history.shutdown()
        self.memory.shutdown()
        self.event_bus.shutdown()
        self.temp_dir.cleanup()

    def test_completed_run_is_recorded_with_its_reports(self) -> None:
        self.planner.plan_project.return_value = make_report_mock(
            {"goal": {"goal": "Todo"}}
        )
        self.architect.design_architecture.return_value = make_report_mock(
            {"project_id": "todo"}
        )
        workflow = self.workflow_service.create_workflow(
            WorkflowType.BUILD_ONLY, "Todo run", "Build a todo app"
        )
        # Narrow the stages to the two mocked services.
        workflow.stages = [
            s for s in workflow.stages if s.name in ("planner", "architect")
        ]

        self.workflow_service.run_workflow(workflow)

        run = self.history.get_run(workflow.id)
        assert run is not None
        self.assertEqual(run.summary.goal, "Build a todo app")
        self.assertEqual(run.summary.state, "COMPLETED")
        self.assertEqual(run.summary.progress, 100.0)
        self.assertEqual(
            run.artifact_kinds, ["architecture_specification", "project_plan"]
        )
        self.assertEqual(
            self.history.get_artifact(workflow.id, "project_plan"),
            {"goal": {"goal": "Todo"}},
        )

    def test_failed_run_is_recorded_with_its_error(self) -> None:
        self.planner.plan_project.side_effect = RuntimeError("model unavailable")
        workflow = self.workflow_service.create_workflow(
            WorkflowType.BUILD_ONLY, "Doomed", "Build something"
        )
        workflow.stages = [s for s in workflow.stages if s.name == "planner"]
        workflow.stages[0].retry_count = 0

        with self.assertRaises(Exception):
            self.workflow_service.run_workflow(workflow)

        run = self.history.get_run(workflow.id)
        assert run is not None
        self.assertEqual(run.summary.state, "FAILED")
        self.assertIn("planner", run.errors)

    def test_second_run_does_not_overwrite_first_runs_reports(self) -> None:
        ids = []
        for title in ("First", "Second"):
            self.planner.plan_project.return_value = make_report_mock(
                {"goal": {"goal": title}}
            )
            wf = self.workflow_service.create_workflow(
                WorkflowType.BUILD_ONLY, title, title
            )
            wf.stages = [s for s in wf.stages if s.name == "planner"]
            self.workflow_service.run_workflow(wf)
            ids.append(wf.id)

        first = self.history.get_artifact(ids[0], "project_plan")
        second = self.history.get_artifact(ids[1], "project_plan")
        assert first is not None and second is not None
        self.assertEqual(first["goal"]["goal"], "First")
        self.assertEqual(second["goal"]["goal"], "Second")

    def test_history_failure_does_not_break_the_workflow(self) -> None:
        self.planner.plan_project.return_value = make_report_mock({"goal": {}})
        self.history.shutdown()  # every record call now raises HistoryError
        workflow = self.workflow_service.create_workflow(
            WorkflowType.BUILD_ONLY, "Resilient", "Goal"
        )
        workflow.stages = [s for s in workflow.stages if s.name == "planner"]

        report = self.workflow_service.run_workflow(workflow)

        self.assertEqual(report["status"], "COMPLETED")
        self.history = ForgeAIHistoryService(":memory:")
        self.history.initialize()


if __name__ == "__main__":
    unittest.main()
