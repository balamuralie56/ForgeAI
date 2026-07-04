"""
Unit and integration tests for the ForgeAI Logging Engine.
"""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from forge_core.configuration.models import SystemSettings
from forge_core.logging.engine import LoggingEngine


class MockConfigService:
    """Mock ConfigurationService for testing."""

    def __init__(self, log_dir: str):
        self._log_dir = log_dir

    def get_system_settings(self) -> SystemSettings:
        return SystemSettings(log_dir=self._log_dir, log_level="DEBUG")


class TestLoggingEngine(unittest.TestCase):
    """Test suite for the Logging Engine and Formatters."""

    def setUp(self) -> None:
        """Sets up a temporary directory and initializes the engine."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.config_service = MockConfigService(self.test_dir.name)
        self.engine = LoggingEngine(self.config_service)  # type: ignore
        self.logger = self.engine.get_root_logger()

    def tearDown(self) -> None:
        """Shuts down the engine and cleans up temp files."""
        self.engine.shutdown()
        self.test_dir.cleanup()

    def test_json_formatting_and_context(self) -> None:
        """Test that logs correctly format as JSON and bind context."""
        module_logger = self.logger.get_logger("PlannerPlugin")
        bound_logger = module_logger.bind_context(task_id="tsk_123")

        bound_logger.info("Analyzing requirements")
        self.engine.shutdown()  # Force flush to disk

        log_file = Path(self.test_dir.name) / "forge.log"
        self.assertTrue(log_file.exists())

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])

        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["module"], "ForgeAI.PlannerPlugin")
        self.assertEqual(data["message"], "Analyzing requirements")
        self.assertEqual(data["task_id"], "tsk_123")

    def test_thread_safety_concurrency(self) -> None:
        """
        Stress test to ensure the non-blocking queue drops no logs
        when blasted by multiple threads simultaneously.
        """
        thread_count = 50
        logs_per_thread = 100
        total_expected_logs = thread_count * logs_per_thread

        def worker_task(thread_id: int) -> None:
            worker_logger = self.logger.bind_context(t_id=thread_id)
            for i in range(logs_per_thread):
                worker_logger.debug(f"Message {i} from thread {thread_id}")

        threads = []
        for i in range(thread_count):
            t = threading.Thread(target=worker_task, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Stop listener to flush the queue to disk
        self.engine.shutdown()

        log_file = Path(self.test_dir.name) / "forge.log"
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertEqual(
            len(lines),
            total_expected_logs,
            "Logs were dropped during concurrent writes.",
        )


if __name__ == "__main__":
    unittest.main()
