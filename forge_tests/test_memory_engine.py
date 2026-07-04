"""
Unit tests for the ForgeAI Memory Engine.
Validates Runtime Memory, Project Memory, and SQLite persistence.
"""

import tempfile
import unittest
from pathlib import Path

from forge_core.memory import ForgeAIMemoryService


class TestMemoryEngine(unittest.TestCase):
    """Test suite verifying in-memory state tracking and durable database mapping."""

    def setUp(self) -> None:
        """Initializes a temporary database for test runs."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.db"
        self.memory_service = ForgeAIMemoryService(db_path=str(self.db_path))
        self.memory_service.initialize()

    def tearDown(self) -> None:
        """Cleans up the database resources."""
        self.memory_service.shutdown()
        self.temp_dir.cleanup()

    def test_runtime_memory_state_isolation(self) -> None:
        """Tests execution and project state additions and updates inside RuntimeMemory."""
        runtime = self.memory_service.runtime

        # Test execution states
        runtime.set_execution_state("status", "running")
        runtime.set_execution_state("stage", 3)
        self.assertEqual(runtime.get_execution_state("status"), "running")
        self.assertEqual(runtime.get_execution_state("stage"), 3)
        self.assertIsNone(runtime.get_execution_state("non_existent"))

        # Test active tasks
        runtime.add_active_task("task_1", {"name": "Test Task"})
        self.assertIn("task_1", runtime.get_active_tasks())
        self.assertEqual(runtime.get_active_tasks()["task_1"]["name"], "Test Task")

        runtime.remove_active_task("task_1")
        self.assertNotIn("task_1", runtime.get_active_tasks())

        # Test plugin registry
        runtime.register_loaded_plugin("test_plugin", "1.2.0", {"setting": True})
        plugins = runtime.get_loaded_plugins()
        self.assertIn("test_plugin", plugins)
        self.assertEqual(plugins["test_plugin"]["version"], "1.2.0")

        # Test project states
        runtime.set_project_state("git_root", "/project")
        self.assertEqual(runtime.get_project_state("git_root"), "/project")

        # Test clear
        runtime.clear()
        self.assertIsNone(runtime.get_execution_state("status"))
        self.assertEqual(len(runtime.get_active_tasks()), 0)
        self.assertEqual(len(runtime.get_loaded_plugins()), 0)

    def test_project_memory_persistence(self) -> None:
        """Tests metadata, files, architecture decision logs, and completed tasks persistence."""
        project = self.memory_service.project

        # 1. Metadata
        project.set_metadata("project_name", "ForgeAI Test")
        self.assertEqual(project.get_metadata("project_name"), "ForgeAI Test")
        self.assertEqual(
            project.get_metadata("not_exists", "default_val"), "default_val"
        )

        # 2. Generated Files
        project.record_generated_file("src/main.py", "hash123", {"lines": 50})
        files = project.get_generated_files()
        self.assertIn("src/main.py", files)
        self.assertEqual(files["src/main.py"]["content_hash"], "hash123")
        self.assertEqual(files["src/main.py"]["metadata"]["lines"], 50)

        # 3. Architecture logs
        project.add_architecture_history("Use SQLite for persistence")
        history = project.get_architecture_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["entry"], "Use SQLite for persistence")

        # 4. Completed Tasks
        project.record_completed_task("task_001", {"success": True})
        tasks = project.get_completed_tasks()
        self.assertIn("task_001", tasks)
        self.assertEqual(tasks["task_001"]["result"]["success"], True)

    def test_db_persistence_across_reboots(self) -> None:
        """Tests that Project Memory persists correctly to disk across Service restarts."""
        # Write to first database instance
        project = self.memory_service.project
        project.set_metadata("unique_key", "saved_value")
        project.record_generated_file("app.py", "md5hash")

        # Shut down first service
        self.memory_service.shutdown()

        # Instantiate new memory service using the same database file
        new_service = ForgeAIMemoryService(db_path=str(self.db_path))
        new_service.initialize()

        try:
            new_project = new_service.project
            # Verify data is loaded from sqlite3 correctly
            self.assertEqual(new_project.get_metadata("unique_key"), "saved_value")

            files = new_project.get_generated_files()
            self.assertIn("app.py", files)
            self.assertEqual(files["app.py"]["content_hash"], "md5hash")
        finally:
            new_service.shutdown()


if __name__ == "__main__":
    unittest.main()
