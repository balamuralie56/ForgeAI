"""
Unit and integration tests for the ForgeAI Launcher.
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Adjusting path so it can find the launcher in the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from launcher import ForgeAILauncher


class TestForgeAILauncher(unittest.TestCase):
    """Test suite for the system bootstrapper and launcher."""

    def setUp(self) -> None:
        """Redirect stdout to capture the banner and isolate filesystem tests."""
        self.captured_output = io.StringIO()
        self.original_stdout = sys.stdout
        sys.stdout = self.captured_output
        
        # Change working directory to a temp dir so we don't pollute the actual project root during tests
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir.name)
        
        # Create a mock defaults.json so the ConfigurationManager can boot successfully
        self.config_dir = Path("config")
        self.config_dir.mkdir()
        defaults_file = self.config_dir / "defaults.json"
        defaults_file.write_text("""
        {
            "version": "0.1",
            "schema_version": "1.0",
            "system": {"workspace_dir": "forge_workspace", "log_dir": "forge_data/logs", "log_level": "INFO"},
            "models": {"provider": "ollama", "default_model": "qwen2.5-coder:7b", "base_url": "http://localhost:11434", "temperature": 0.7, "max_tokens": 8192},
            "plugins": {"plugin_dir": "forge_plugins", "enabled_plugins": []}
        }
        """, encoding="utf-8")

        self.launcher = ForgeAILauncher()

    def tearDown(self) -> None:
        """Restore stdout and clean up temp directory."""
        sys.stdout = self.original_stdout
        
        if self.launcher.logging_engine:
            self.launcher.shutdown()
            
        os.chdir(self.original_cwd)
        self.test_dir.cleanup()

    def test_directory_creation(self) -> None:
        """Verifies that the launcher correctly creates all required nested directories."""
        self.launcher.ensure_directories()
        
        expected_dirs = [
            "forge_workspace",
            "forge_data",
            "forge_data/logs",
            "forge_data/cache",
            "forge_data/backups",
            "forge_data/databases",
            "forge_data/embeddings"
        ]
        
        for dir_path in expected_dirs:
            self.assertTrue(Path(dir_path).exists(), f"Required directory {dir_path} was not created.")
            self.assertTrue(Path(dir_path).is_dir(), f"Path {dir_path} is not a directory.")

    def test_boot_banner_output(self) -> None:
        """Verifies the boot sequence completes and outputs the correct exact banner."""
        exit_code = self.launcher.boot()
        
        self.assertEqual(exit_code, 0, "Launcher failed to boot with exit code 0.")
        
        output = self.captured_output.getvalue()
        self.assertIn("ForgeAI Operating System", output)
        self.assertIn("Loading Configuration...           ✓ Success", output)
        self.assertIn("Workspace...                       ✓ Ready", output)
        self.assertIn("Kernel...                          ✓ Ready", output)
        self.assertIn("ForgeAI Ready", output)

    def test_graceful_shutdown(self) -> None:
        """Verifies the logging engine receives the shutdown command."""
        self.launcher.boot()
        self.assertIsNotNone(self.launcher.logging_engine)
        
        with patch.object(self.launcher.logging_engine, 'shutdown') as mock_shutdown:
            self.launcher.shutdown()
            mock_shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()