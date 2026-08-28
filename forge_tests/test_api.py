"""
Tests for the ForgeAI Web API (forge_api/). Boots a dedicated test Kernel from
an isolated temp working directory (the Kernel resolves its config, workspace,
and memory DB paths relative to cwd), so these tests never touch the real
forge_data/databases/project_memory.db or forge_workspace/ a local run uses.

Note: these calls deliberately do NOT use `with client:` - that would trigger
the app's lifespan (which boots its own Kernel via bootstrap.get_kernel()).
Since cls.test_kernel is already booted and injected into bootstrap._kernel
directly, the route handlers work correctly without ever running lifespan.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from forge_api import bootstrap, runner
from forge_core.kernel.kernel import ForgeAIKernel


class TestForgeAPI(unittest.TestCase):
    """Test suite covering the REST endpoints against an isolated test Kernel."""

    original_cwd: str
    temp_dir: tempfile.TemporaryDirectory
    workspace: Path
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

        cls.workspace = Path(cls.temp_dir.name) / "forge_workspace"

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
        # Ensure no leftover "running" flag blocks a fresh create-workflow test.
        runner._active_workflow_id = None

    # ─── Diagnostics ─────────────────────────────────────────────────────────

    def test_diagnostics_endpoint(self) -> None:
        response = self.client.get("/api/diagnostics")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "0.9.5")
        self.assertIn("reviewer", body["enabled_plugins"])
        self.assertIn("security", body["enabled_plugins"])

    # ─── Workflow creation & validation ──────────────────────────────────────

    def test_create_workflow_rejects_unknown_type(self) -> None:
        response = self.client.post(
            "/api/workflows",
            json={"goal": "Build a todo app", "workflow_type": "NOT_REAL"},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_workflow_starts_in_background(self) -> None:
        with patch.object(runner, "start_workflow") as mock_start:
            response = self.client.post(
                "/api/workflows", json={"goal": "Build a todo app"}
            )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("workflow_id", body)
        self.assertEqual(body["status"], "PENDING")
        mock_start.assert_called_once()

    def test_create_workflow_returns_409_when_already_running(self) -> None:
        with patch.object(
            runner,
            "start_workflow",
            side_effect=runner.WorkflowAlreadyRunningError("busy"),
        ):
            response = self.client.post(
                "/api/workflows", json={"goal": "Build a todo app"}
            )
        self.assertEqual(response.status_code, 409)

    # ─── Workflow status ─────────────────────────────────────────────────────

    def test_get_workflow_not_found(self) -> None:
        response = self.client.get("/api/workflows/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_get_workflow_returns_created_status(self) -> None:
        with patch.object(runner, "start_workflow"):
            create_resp = self.client.post(
                "/api/workflows", json={"goal": "Build a todo app"}
            )
            workflow_id = create_resp.json()["workflow_id"]

            status_resp = self.client.get(f"/api/workflows/{workflow_id}")

        self.assertEqual(status_resp.status_code, 200)
        body = status_resp.json()
        self.assertEqual(body["id"], workflow_id)
        self.assertEqual(body["state"], "PENDING")
        self.assertGreaterEqual(len(body["stages"]), 8)  # incl. reviewer stage

    # ─── Workspace files ─────────────────────────────────────────────────────

    def test_list_files_for_unknown_workflow(self) -> None:
        response = self.client.get("/api/workflows/does-not-exist/files")
        self.assertEqual(response.status_code, 404)

    def test_list_and_read_generated_files(self) -> None:
        with patch.object(runner, "start_workflow"):
            create_resp = self.client.post(
                "/api/workflows", json={"goal": "Build a todo app"}
            )
            workflow_id = create_resp.json()["workflow_id"]

            self.workspace.mkdir(parents=True, exist_ok=True)
            (self.workspace / "app.py").write_text("print('hello')\n", encoding="utf-8")

            list_resp = self.client.get(f"/api/workflows/{workflow_id}/files")
            self.assertEqual(list_resp.status_code, 200)
            paths = [f["path"] for f in list_resp.json()["files"]]
            self.assertIn("app.py", paths)

            content_resp = self.client.get(f"/api/workflows/{workflow_id}/files/app.py")
            self.assertEqual(content_resp.status_code, 200)
            self.assertIn("hello", content_resp.json()["content"])

    def test_file_path_traversal_is_rejected(self) -> None:
        with patch.object(runner, "start_workflow"):
            create_resp = self.client.post(
                "/api/workflows", json={"goal": "Build a todo app"}
            )
            workflow_id = create_resp.json()["workflow_id"]

            response = self.client.get(
                f"/api/workflows/{workflow_id}/files/..%2F..%2Fforge.json"
            )
        self.assertIn(response.status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()
