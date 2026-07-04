"""
Unit and integration tests for the ForgeAI Kernel, Service Registry, and Lifecycles.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from forge_core.configuration.exceptions import ConfigurationValidationError
from forge_core.configuration.service import ConfigurationService
from forge_core.kernel.exceptions import KernelError, ServiceNotFoundError
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.kernel.lifecycle import LifecycleComponent, LifecycleManager
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.logging.service import LoggingService
from forge_core.model_router.service import ModelRouterService
from forge_core.plugin_manager.service import PluginManagerService


class MockService:
    """Mock interface representation for DI testing."""
    pass


class ConcreteMockService(MockService):
    """Concrete implementation of MockService."""
    pass


class DummyLifecycleComponent(LifecycleComponent):
    """Dummy component tracking lifecycle order transitions."""

    def __init__(self, name: str, execution_log: list) -> None:
        self.name = name
        self.execution_log = execution_log

    def initialize(self) -> None:
        self.execution_log.append(f"init_{self.name}")

    def shutdown(self) -> None:
        self.execution_log.append(f"shutdown_{self.name}")


class TestServiceRegistry(unittest.TestCase):
    """Test suite for the ServiceRegistry (Dependency Injection)."""

    def setUp(self) -> None:
        self.registry = ServiceRegistry()

    def test_register_and_resolve_success(self) -> None:
        instance = ConcreteMockService()
        self.registry.register(MockService, instance)
        resolved = self.registry.resolve(MockService)
        self.assertEqual(resolved, instance)

    def test_resolve_unregistered_raises_error(self) -> None:
        with self.assertRaises(ServiceNotFoundError):
            self.registry.resolve(MockService)

    def test_register_none_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.register(MockService, None)  # type: ignore


class TestLifecycleManager(unittest.TestCase):
    """Test suite for LifecycleManager orchestrator."""

    def setUp(self) -> None:
        self.manager = LifecycleManager()
        self.execution_log: list = []

    def test_lifecycle_order_execution(self) -> None:
        comp_a = DummyLifecycleComponent("A", self.execution_log)
        comp_b = DummyLifecycleComponent("B", self.execution_log)
        
        self.manager.register(comp_a)
        self.manager.register(comp_b)
        
        self.manager.initialize_all()
        self.assertEqual(self.execution_log, ["init_A", "init_B"])
        
        self.manager.shutdown_all()
        self.assertEqual(self.execution_log, ["init_A", "init_B", "shutdown_B", "shutdown_A"])

    def test_shutdown_handles_exceptions_gracefully(self) -> None:
        comp_good = DummyLifecycleComponent("Good", self.execution_log)
        comp_bad = MagicMock(spec=LifecycleComponent)
        comp_bad.shutdown.side_effect = Exception("Teardown failure")

        self.manager.register(comp_good)
        self.manager.register(comp_bad)

        self.manager.initialize_all()
        
        # Test that exception in comp_bad doesn't halt the reverse shutdown chain
        with self.assertLogs("ForgeAI.LifecycleManager", level="ERROR") as log:
            self.manager.shutdown_all()
            self.assertIn("Unhandled error occurred during shutdown of MagicMock", log.output[0])
        
        self.assertEqual(self.execution_log, ["init_Good", "shutdown_Good"])


class TestForgeAIKernel(unittest.TestCase):
    """Test suite for ForgeAIKernel booting and registry binding."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = Path(self.temp_dir.name) / "forge.json"
        self.defaults_file = Path(self.temp_dir.name) / "defaults.json"
        
        # Write dummy configs
        self.defaults_file.write_text("""
        {
            "version": "1.0",
            "schema_version": "1.0",
            "system": {"workspace_dir": "test_workspace", "log_dir": "test_logs", "log_level": "INFO"},
            "models": {"provider": "ollama", "default_model": "qwen", "base_url": "http://localhost:11434", "temperature": 0.7, "max_tokens": 100},
            "plugins": {"plugin_dir": "test_plugins", "enabled_plugins": []}
        }
        """, encoding="utf-8")

        self.kernel = ForgeAIKernel(
            config_path=str(self.config_file),
            defaults_path=str(self.defaults_file)
        )

    def tearDown(self) -> None:
        self.kernel.shutdown()
        self.temp_dir.cleanup()

    def test_kernel_boot_success(self) -> None:
        self.kernel.boot()
        self.assertTrue(self.kernel._booted)
        
        # Check standard registered services
        self.assertIsNotNone(self.kernel.registry.resolve(ConfigurationService))
        self.assertIsNotNone(self.kernel.registry.resolve(LoggingService))
        self.assertIsNotNone(self.kernel.registry.resolve(ModelRouterService))
        self.assertIsNotNone(self.kernel.registry.resolve(PluginManagerService))

    def test_kernel_boot_failure_rollback(self) -> None:
        # Cause dynamic configuration load failure (malformed default schema)
        self.defaults_file.write_text("invalid json", encoding="utf-8")
        
        with self.assertRaises(KernelError):
            self.kernel.boot()
            
        self.assertFalse(self.kernel._booted)
        # Ensure log engine shutdown was processed
        self.assertIsNone(self.kernel.logging_engine)


if __name__ == "__main__":
    unittest.main()
