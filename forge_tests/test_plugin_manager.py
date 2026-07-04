"""
Unit tests for the ForgeAI Plugin Manager.
Tests dynamic package discovery, class inspection, and integration.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from forge_core.plugin_manager.manager import PluginManager


class TestPluginManager(unittest.TestCase):
    """Test suite for dynamic plugin lifecycle operations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugin_dir_path = Path(self.temp_dir.name) / "test_plugins"
        self.plugin_dir_path.mkdir()
        
        self.registry = ServiceRegistry()
        self.original_sys_path = sys.path.copy()

    def tearDown(self) -> None:
        sys.path = self.original_sys_path
        self.temp_dir.cleanup()

    def _create_mock_plugin(self, name: str, code_content: str) -> None:
        """Helper to write a physical mock plugin folder and python file."""
        folder = self.plugin_dir_path / name
        folder.mkdir()
        init_file = folder / "__init__.py"
        init_file.write_text(code_content, encoding="utf-8")

    def test_load_plugin_success(self) -> None:
        code = """
from forge_core.plugin_manager.interface import Plugin
from forge_core.kernel.service_registry import ServiceRegistry

class MockTestPlugin(Plugin):
    @property
    def name(self) -> str:
        return "MockTest"

    @property
    def version(self) -> str:
        return "1.0.2"

    def initialize(self, registry: ServiceRegistry) -> None:
        registry.register(str, "initialized_string_value")

    def shutdown(self) -> None:
        pass
"""
        self._create_mock_plugin("mock_test", code)
        
        manager = PluginManager(
            plugin_dir=str(self.plugin_dir_path),
            enabled_plugins=["mock_test"],
            registry=self.registry
        )
        
        manager.load_plugins()
        
        loaded = manager.get_plugin("MockTest")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "MockTest")  # type: ignore
        self.assertEqual(loaded.version, "1.0.2")  # type: ignore
        
        # Verify initialize was called and registered the string
        self.assertEqual(self.registry.resolve(str), "initialized_string_value")
        
        manager.shutdown_all()
        self.assertEqual(len(manager.get_all_plugins()), 0)

    def test_missing_plugin_folder_skips_gracefully(self) -> None:
        manager = PluginManager(
            plugin_dir=str(self.plugin_dir_path),
            enabled_plugins=["missing_folder_plugin"],
            registry=self.registry
        )
        
        # Should not raise error
        with self.assertLogs("ForgeAI.PluginManager", level="WARNING") as logs:
            manager.load_plugins()
            self.assertIn("Enabled plugin directory is missing", logs.output[0])
            
        self.assertEqual(len(manager.get_all_plugins()), 0)

    def test_empty_plugin_folder_skips_gracefully(self) -> None:
        # Create folder but no __init__.py/code
        folder = self.plugin_dir_path / "empty_plugin"
        folder.mkdir()
        
        manager = PluginManager(
            plugin_dir=str(self.plugin_dir_path),
            enabled_plugins=["empty_plugin"],
            registry=self.registry
        )
        
        with self.assertLogs("ForgeAI.PluginManager", level="WARNING") as logs:
            manager.load_plugins()
            self.assertTrue(any(
                "Failed to import plugin" in line or "No concrete class subclassing" in line
                for line in logs.output
            ))
            
        self.assertEqual(len(manager.get_all_plugins()), 0)

    def test_malformed_plugin_class_skips(self) -> None:
        # Create package but class does not inherit from Plugin interface
        code = """
class MalformedClass:
    @property
    def name(self) -> str:
        return "Malformed"
"""
        self._create_mock_plugin("malformed", code)
        
        manager = PluginManager(
            plugin_dir=str(self.plugin_dir_path),
            enabled_plugins=["malformed"],
            registry=self.registry
        )
        
        with self.assertLogs("ForgeAI.PluginManager", level="WARNING") as logs:
            manager.load_plugins()
            self.assertIn("No concrete class subclassing 'Plugin' found", logs.output[0])
            
        self.assertEqual(len(manager.get_all_plugins()), 0)


if __name__ == "__main__":
    unittest.main()
