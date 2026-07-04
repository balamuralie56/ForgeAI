"""
Unit and integration tests to boost test coverage of the ForgeAI core packages above 90%.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.event_bus import ForgeAIEventBus
from forge_core.memory import ForgeAIMemoryService, SQLitePersistenceProvider
from forge_core.model_router.router import ModelRouter
from forge_core.model_router.providers import OpenAICompatibleProvider
from forge_core.task_engine import (
    ForgeAITaskEngine,
    Task,
    TaskDAG,
    TaskState,
)


class TestCoverageBoost(unittest.TestCase):
    """Targeted coverage tests for core engines."""

    def test_topological_sort(self) -> None:
        """Verifies topological sorting execution path."""
        task_1 = Task("1", "T1", lambda: None)
        task_2 = Task("2", "T2", lambda: None, dependencies=["1"])
        dag = TaskDAG([task_1, task_2])

        sort = dag.get_topological_sort()
        self.assertEqual(sort, ["1", "2"])

    def test_model_router_fallback_and_routing(self) -> None:
        """Tests fallback client instantiation and route parameters coverage."""
        # Mock configuration for fallback provider name
        temp_dir = tempfile.TemporaryDirectory()
        defaults_file = Path(temp_dir.name) / "defaults.json"
        defaults_file.write_text(
            """
        {
            "version": "1.0",
            "schema_version": "1.0",
            "system": {"workspace_dir": "test_workspace", "log_dir": "test_logs", "log_level": "INFO"},
            "models": {"provider": "custom_llm", "default_model": "custom_m", "base_url": "http://localhost:8000", "temperature": 0.5, "max_tokens": 100},
            "plugins": {"plugin_dir": "test_plugins", "enabled_plugins": []}
        }
        """,
            encoding="utf-8",
        )

        config = ConfigurationManager(
            config_path=str(Path(temp_dir.name) / "forge.json"),
            defaults_path=str(defaults_file),
        )
        router = ModelRouter(config)

        # Check fallback to OpenAICompatibleProvider
        provider = router.get_provider("custom_llm")
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertEqual(provider.name, "custom_llm")

        # Mock calls
        provider.generate = MagicMock(return_value=None)  # type: ignore[method-assign]
        provider.generate_chat = MagicMock(return_value=None)  # type: ignore[method-assign]

        router.generate("hello", provider="custom_llm")
        provider.generate.assert_called_once()

        router.generate_chat([{"role": "user", "content": "hi"}], provider="custom_llm")
        provider.generate_chat.assert_called_once()
        temp_dir.cleanup()

    def test_task_engine_edge_cases(self) -> None:
        """Covers error cases and cancellations in the Task Engine coordinator."""
        event_bus = ForgeAIEventBus()
        event_bus.initialize()
        memory = ForgeAIMemoryService(db_path=":memory:")
        memory.initialize()

        engine = ForgeAITaskEngine(event_bus, memory)
        engine.initialize()

        # 1. Invalid submission type raises TypeError
        with self.assertRaises(TypeError):
            engine.submit_dag("not a dag instance")

        # 2. Cancel non-active scheduler
        engine.cancel_dag("non-existent-dag-id")

        # 3. State lookup on non-active run
        with self.assertRaises(KeyError):
            engine.get_dag_state("invalid-id")

        # 4. execute_dag on non-active run
        with self.assertRaises(KeyError):
            asyncio.run(engine.execute_dag("invalid-id"))

        engine.shutdown()
        memory.shutdown()
        event_bus.shutdown()

    def test_sqlite_persistence_edge_cases(self) -> None:
        """Covers deletion, missing values, and closed DB exceptions in persistence.py."""
        provider = SQLitePersistenceProvider(db_path=":memory:")
        provider.initialize()

        # Key deletions
        provider.set("test_key", "val")
        self.assertEqual(provider.get("test_key"), "val")
        provider.delete("test_key")
        self.assertIsNone(provider.get("test_key"))

        # Close and assert errors
        provider.close()
        with self.assertRaises(RuntimeError):
            provider.get("test_key")
        with self.assertRaises(RuntimeError):
            provider.set("test_key", "val")
        with self.assertRaises(RuntimeError):
            provider.delete("test_key")

    def test_scheduler_cancellation(self) -> None:
        """Covers task cancellation within the TaskScheduler run loop."""

        async def mock_long_task() -> None:
            await asyncio.sleep(0.5)

        task = Task("long", "Long running task", mock_long_task)
        dag = TaskDAG([task])

        event_bus = ForgeAIEventBus()
        event_bus.initialize()
        memory = ForgeAIMemoryService(db_path=":memory:")
        memory.initialize()
        engine = ForgeAITaskEngine(event_bus, memory)
        engine.initialize()

        run_id = engine.submit_dag(dag)

        # Trigger execution and cancel it asynchronously
        async def run_and_cancel() -> None:
            exec_task = asyncio.create_task(engine.execute_dag(run_id))
            await asyncio.sleep(0.02)
            engine.cancel_dag(run_id)
            try:
                await exec_task
            except Exception:
                pass

        asyncio.run(run_and_cancel())
        self.assertEqual(task.state, TaskState.CANCELLED)

        engine.shutdown()
        memory.shutdown()
        event_bus.shutdown()


if __name__ == "__main__":
    unittest.main()
