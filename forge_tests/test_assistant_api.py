"""
Tests for the Assistant endpoints of the ForgeAI Web API (/api/assistant/*).
Boots an isolated test Kernel in a temp working directory (so real databases
are never touched) and replaces the model router's streaming call with a
scripted reply, so no model is needed.
"""

import json
import sys
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterator, List
from unittest.mock import patch

from fastapi.testclient import TestClient

from forge_api import bootstrap
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.model_router.service import ChatChunk

HEADERS = {"X-ForgeAI-Client": "test"}
REPLY = """Add a count method.

store.py
<<<<<<< SEARCH
    def add(self, item):
        self.items.append(item)
=======
    def add(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)
>>>>>>> REPLACE
"""
STORE = "class Store:\n    def __init__(self):\n        self.items = []\n\n    def add(self, item):\n        self.items.append(item)\n"


def scripted_stream(*_: Any, **__: Any) -> Iterator[ChatChunk]:
    for i in range(0, len(REPLY), 20):
        yield ChatChunk(text=REPLY[i : i + 20])
    yield ChatChunk(text="", done=True, usage={"completion_tokens": 9})


class TestAssistantAPI(unittest.TestCase):
    original_cwd: str
    temp_dir: tempfile.TemporaryDirectory
    test_kernel: ForgeAIKernel
    client: TestClient
    project: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.original_cwd = os.getcwd()
        cls.temp_dir = tempfile.TemporaryDirectory()
        base = Path(cls.temp_dir.name)
        shutil.copytree(Path(cls.original_cwd) / "config", base / "config")
        shutil.copytree(
            Path(cls.original_cwd) / "forge_plugins",
            base / "forge_plugins",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        cls.project = base / "project"
        cls.project.mkdir()
        os.chdir(cls.temp_dir.name)
        cls.test_kernel = ForgeAIKernel(
            config_path="forge.json", defaults_path="config/defaults.json"
        )
        cls.test_kernel.boot()
        bootstrap._kernel = cls.test_kernel

        from forge_api.main import app

        cls.client = TestClient(app, base_url="http://127.0.0.1:8420")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.test_kernel.shutdown()
        bootstrap._kernel = None
        os.chdir(cls.original_cwd)
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        (self.project / "store.py").write_text(STORE, encoding="utf-8")
        for conversation in self.client.get(
            "/api/assistant/conversations", headers=HEADERS
        ).json()["conversations"]:
            self.client.delete(
                f"/api/assistant/conversations/{conversation['id']}", headers=HEADERS
            )

    def create(self, **body: Any) -> Dict[str, Any]:
        response = self.client.post(
            "/api/assistant/conversations",
            headers=HEADERS,
            json={"project_root": str(self.project), **body},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def send(
        self, conversation_id: str, content: str, mode: str = "edit"
    ) -> List[Dict[str, Any]]:
        assert self.test_kernel.model_router is not None
        with patch.object(
            self.test_kernel.model_router, "stream_chat", side_effect=scripted_stream
        ):
            response = self.client.post(
                f"/api/assistant/conversations/{conversation_id}/messages",
                headers=HEADERS,
                json={"content": content, "mode": mode},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/x-ndjson")
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_requests_without_client_header_are_refused(self) -> None:
        self.assertEqual(self.client.get("/api/assistant/status").status_code, 403)

    def test_requests_to_non_loopback_host_are_refused(self) -> None:
        response = self.client.get(
            "/api/assistant/status", headers={**HEADERS, "Host": "evil.example:8420"}
        )
        self.assertEqual(response.status_code, 403)
        ipv6 = self.client.get(
            "/api/assistant/status", headers={**HEADERS, "Host": "[::1]:8420"}
        )
        self.assertEqual(ipv6.status_code, 200)

    def test_status(self) -> None:
        body = self.client.get("/api/assistant/status", headers=HEADERS).json()
        self.assertIn("model", body)
        self.assertIn("storage", body)
        self.assertFalse(body["build_running"])

    def test_create_validates_project_folder(self) -> None:
        response = self.client.post(
            "/api/assistant/conversations",
            headers=HEADERS,
            json={"project_root": str(self.project / "missing")},
        )
        self.assertEqual(response.status_code, 400)

    def test_full_edit_flow(self) -> None:
        conversation = self.create()
        events = self.send(conversation["id"], "add a count method")
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "message")
        self.assertIn("token", types)
        self.assertEqual(types[-1], "done")
        change = [e for e in events if e["type"] == "change_set"][0]["change_set"]
        self.assertEqual(change["status"], "pending")

        detail = self.client.get(
            f"/api/assistant/conversations/{conversation['id']}", headers=HEADERS
        ).json()
        self.assertEqual([m["role"] for m in detail["messages"]], ["user", "assistant"])
        self.assertEqual(detail["conversation"]["title"], "add a count method")
        self.assertFalse(detail["busy"])

        applied = self.client.post(
            f"/api/assistant/changes/{change['id']}/apply", headers=HEADERS
        )
        self.assertEqual(applied.json()["change_set"]["status"], "applied")
        self.assertIn("def count", (self.project / "store.py").read_text())
        again = self.client.post(
            f"/api/assistant/changes/{change['id']}/apply", headers=HEADERS
        )
        self.assertEqual(again.status_code, 409)

        reverted = self.client.post(
            f"/api/assistant/changes/{change['id']}/revert", headers=HEADERS
        )
        self.assertEqual(reverted.json()["change_set"]["status"], "reverted")
        self.assertEqual((self.project / "store.py").read_text(), STORE)

    def test_apply_conflict_when_file_changed(self) -> None:
        conversation = self.create()
        change = [
            e
            for e in self.send(conversation["id"], "add count")
            if e["type"] == "change_set"
        ][0]["change_set"]
        (self.project / "store.py").write_text(
            STORE + "\n# edited by hand\n", encoding="utf-8"
        )
        response = self.client.post(
            f"/api/assistant/changes/{change['id']}/apply", headers=HEADERS
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("changed after", response.json()["detail"])

    def test_update_list_files_check_and_delete(self) -> None:
        conversation = self.create()
        cid = conversation["id"]
        self.assertEqual(
            self.client.post(
                f"/api/assistant/conversations/{cid}/check", headers=HEADERS
            ).status_code,
            400,
        )
        updated = self.client.patch(
            f"/api/assistant/conversations/{cid}",
            headers=HEADERS,
            json={
                "check_command": f'"{sys.executable}" -c "print(7)"',
                "auto_fix": True,
            },
        ).json()
        self.assertTrue(updated["auto_fix"])
        check = self.client.post(
            f"/api/assistant/conversations/{cid}/check", headers=HEADERS
        ).json()
        self.assertTrue(check["message"]["metadata"]["check"]["passed"])
        files = self.client.get(
            f"/api/assistant/conversations/{cid}/files", headers=HEADERS
        ).json()
        self.assertEqual(files["files"], ["store.py"])
        self.assertFalse(
            self.client.post(
                f"/api/assistant/conversations/{cid}/stop", headers=HEADERS
            ).json()["stopped"]
        )
        self.assertTrue(
            self.client.delete(
                f"/api/assistant/conversations/{cid}", headers=HEADERS
            ).json()["deleted"]
        )
        self.assertEqual(
            self.client.get(
                f"/api/assistant/conversations/{cid}", headers=HEADERS
            ).status_code,
            404,
        )

    def test_unknown_change_and_conversation(self) -> None:
        self.assertEqual(
            self.client.post(
                "/api/assistant/changes/nope/apply", headers=HEADERS
            ).status_code,
            404,
        )
        response = self.client.post(
            "/api/assistant/conversations/nope/messages",
            headers=HEADERS,
            json={"content": "hi"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
