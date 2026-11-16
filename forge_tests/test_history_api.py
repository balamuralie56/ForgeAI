"""
Tests for the History endpoints of the ForgeAI Web API (/api/history/*).
Boots an isolated test Kernel in a temp working directory, like test_api.py, so
the real forge_data/ databases are never touched. Calls deliberately avoid
`with client:` to skip the app lifespan, which would boot a second Kernel.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

from forge_api import bootstrap, runner
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.memory.service import MemoryService


def make_snapshot(
    workflow_id: str,
    created_at: float,
    context: Optional[Dict[str, Any]] = None,
    state: str = "COMPLETED",
) -> Dict[str, Any]:
    return {
        "id": workflow_id,
        "name": f"run {workflow_id}",
        "type": "BUILD_ONLY",
        "state": state,
        "stages": [{"name": "planner", "status": "COMPLETED"}],
        "current_stage_index": 1,
        "context": context if context is not None else {"goal": f"goal {workflow_id}"},
        "errors": {},
        "progress": 100.0,
        "created_at": created_at,
        "updated_at": created_at + 1,
    }


class TestHistoryAPI(unittest.TestCase):
    original_cwd: str
    temp_dir: tempfile.TemporaryDirectory
    test_kernel: ForgeAIKernel
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.original_cwd = os.getcwd()
        cls.temp_dir = tempfile.TemporaryDirectory()
        shutil.copytree(
            Path(cls.original_cwd) / "config", Path(cls.temp_dir.name) / "config"
        )
        shutil.copytree(
            Path(cls.original_cwd) / "forge_plugins",
            Path(cls.temp_dir.name) / "forge_plugins",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        os.chdir(cls.temp_dir.name)

        cls.test_kernel = ForgeAIKernel(
            config_path="forge.json", defaults_path="config/defaults.json"
        )
        cls.test_kernel.boot()
        bootstrap._kernel = cls.test_kernel

        from forge_api.main import app

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.test_kernel.shutdown()
        bootstrap._kernel = None
        os.chdir(cls.original_cwd)
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        runner._active_workflow_id = None
        assert self.test_kernel.history is not None
        for run in self.test_kernel.history.list_runs(limit=200):
            self.test_kernel.history.delete_run(run.workflow_id)

    def _seed(self, workflow_id: str, created_at: float, **kwargs: Any) -> None:
        assert self.test_kernel.history is not None
        self.test_kernel.history.record_run_snapshot(
            make_snapshot(workflow_id, created_at, **kwargs), "qwen2.5-coder:3b"
        )

    def test_history_service_is_registered_and_healthy(self) -> None:
        self.assertEqual(self.test_kernel.health()["services"]["History"], "Ready")

    def test_list_runs_empty(self) -> None:
        body = self.client.get("/api/history/runs").json()
        self.assertEqual(body, {"runs": [], "total": 0, "limit": 50, "offset": 0})

    def test_list_runs_newest_first_with_paging(self) -> None:
        for i in range(3):
            self._seed(f"wf-{i}", 100.0 + i)

        body = self.client.get("/api/history/runs").json()
        self.assertEqual(
            [r["workflow_id"] for r in body["runs"]], ["wf-2", "wf-1", "wf-0"]
        )
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["runs"][0]["model"], "qwen2.5-coder:3b")

        page = self.client.get("/api/history/runs?limit=1&offset=1").json()
        self.assertEqual([r["workflow_id"] for r in page["runs"]], ["wf-1"])
        self.assertEqual(page["total"], 3)

    def test_list_runs_rejects_invalid_paging(self) -> None:
        self.assertEqual(self.client.get("/api/history/runs?limit=0").status_code, 422)
        self.assertEqual(
            self.client.get("/api/history/runs?limit=999").status_code, 422
        )
        self.assertEqual(
            self.client.get("/api/history/runs?offset=-1").status_code, 422
        )

    def test_get_run_detail(self) -> None:
        self._seed("wf-1", 1.0, context={"goal": "g", "project_plan": {"a": 1}})

        body = self.client.get("/api/history/runs/wf-1").json()

        self.assertEqual(body["workflow_id"], "wf-1")
        self.assertEqual(body["artifact_kinds"], ["project_plan"])
        self.assertEqual(body["stages"], [{"name": "planner", "status": "COMPLETED"}])

    def test_get_unknown_run_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/history/runs/nope").status_code, 404)

    def test_get_artifact(self) -> None:
        self._seed("wf-1", 1.0, context={"goal": "g", "project_plan": {"a": 1}})

        body = self.client.get("/api/history/runs/wf-1/artifacts/project_plan").json()

        self.assertEqual(
            body, {"workflow_id": "wf-1", "kind": "project_plan", "data": {"a": 1}}
        )

    def test_get_artifact_unknown_kind_is_404(self) -> None:
        self._seed("wf-1", 1.0)
        response = self.client.get("/api/history/runs/wf-1/artifacts/secrets")
        self.assertEqual(response.status_code, 404)

    def test_get_artifact_not_stored_is_404(self) -> None:
        self._seed("wf-1", 1.0)
        response = self.client.get("/api/history/runs/wf-1/artifacts/test_report")
        self.assertEqual(response.status_code, 404)

    def test_delete_run_removes_history_and_workflow_state(self) -> None:
        self._seed("wf-1", 1.0, context={"goal": "g", "project_plan": {"a": 1}})
        memory = self.test_kernel.registry.resolve(MemoryService)  # type: ignore[type-abstract]
        memory.project.set_metadata("workflow:wf-1", {"id": "wf-1"})

        response = self.client.delete("/api/history/runs/wf-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"workflow_id": "wf-1", "deleted": True})
        self.assertEqual(self.client.get("/api/history/runs/wf-1").status_code, 404)
        self.assertIsNone(memory.project.get_metadata("workflow:wf-1"))
        self.assertEqual(self.client.get("/api/history/runs").json()["total"], 0)

    def test_delete_unknown_run_is_404(self) -> None:
        self.assertEqual(self.client.delete("/api/history/runs/nope").status_code, 404)

    def test_delete_running_run_is_refused_and_keeps_data(self) -> None:
        self._seed("wf-1", 1.0, state="RUNNING")
        runner._active_workflow_id = "wf-1"

        response = self.client.delete("/api/history/runs/wf-1")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/history/runs/wf-1").status_code, 200)

    def test_storage_reports_history_and_workspace(self) -> None:
        self._seed("wf-1", 1.0, context={"goal": "g", "project_plan": {"a": 1}})
        workspace = Path("forge_workspace")
        workspace.mkdir(exist_ok=True)
        (workspace / "out.txt").write_text("12345")

        body = self.client.get("/api/history/storage").json()

        self.assertEqual(body["run_count"], 1)
        self.assertGreater(body["history_database_bytes"], 0)
        self.assertEqual(body["artifact_bytes_by_run"], {"wf-1": len('{"a": 1}')})
        self.assertGreaterEqual(body["workspace_bytes"], 5)

    def test_storage_with_missing_workspace_is_zero(self) -> None:
        shutil.rmtree("forge_workspace", ignore_errors=True)
        body = self.client.get("/api/history/storage").json()
        self.assertEqual(body["workspace_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
