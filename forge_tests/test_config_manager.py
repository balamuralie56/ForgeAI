"""
Unit and integration tests for the Configuration Manager module.
"""

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.exceptions import (
    ConfigurationFileNotFound,
    ConfigurationLoadError,
    ConfigurationValidationError,
)


class TestConfigurationManager(unittest.TestCase):
    """Test suite for the ConfigurationManager class."""

    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.config_file = Path(self.test_dir.name) / "forge.dev.json"
        self.defaults_file = Path(self.test_dir.name) / "defaults.json"

        self.defaults_data: Dict[str, Any] = {
            "version": "1.0",
            "schema_version": "1.0",
            "system": {
                "workspace_dir": "forge_workspace",
                "log_dir": "forge_data/logs",
                "log_level": "INFO",
            },
            "models": {
                "provider": "ollama",
                "default_model": "qwen2.5-coder:7b",
                "base_url": "http://localhost:11434",
                "temperature": 0.7,
                "max_tokens": 8192,
            },
            "plugins": {"plugin_dir": "forge_plugins", "enabled_plugins": ["planner"]},
        }
        self.defaults_file.write_text(json.dumps(self.defaults_data), encoding="utf-8")

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_missing_defaults_file(self) -> None:
        """Issue 4: Tests that missing required defaults file raises ConfigurationFileNotFound."""
        with self.assertRaises(ConfigurationFileNotFound):
            ConfigurationManager(
                config_path=str(self.config_file), defaults_path="does_not_exist.json"
            )

    def test_corrupted_json(self) -> None:
        """Issue 3: Tests that malformed JSON raises a ConfigurationValidationError."""
        self.config_file.write_text("{ abc", encoding="utf-8")

        with self.assertRaises(ConfigurationValidationError):
            ConfigurationManager(
                config_path=str(self.config_file), defaults_path=str(self.defaults_file)
            )

    def test_empty_config_boots(self) -> None:
        """Issue 5: Tests that an empty user config {} boots safely using defaults."""
        self.config_file.write_text("{}", encoding="utf-8")
        manager = ConfigurationManager(
            config_path=str(self.config_file), defaults_path=str(self.defaults_file)
        )

        self.assertEqual(manager.get_model_settings().default_model, "qwen2.5-coder:7b")

    def test_configuration_precedence(self) -> None:
        """
        Issue 7: Tests the strict hierarchy: Environment > User Config > Defaults.
        """
        # 1. Defaults set model to "qwen2.5-coder:7b"

        # 2. User config attempts to override model and log_level
        user_config = {
            "system": {"log_level": "DEBUG"},
            "models": {"default_model": "llama3:8b"},
        }
        self.config_file.write_text(json.dumps(user_config), encoding="utf-8")

        # 3. Environment attempts to override model
        os.environ["FORGE_MODEL"] = "deepseek-coder"

        try:
            manager = ConfigurationManager(
                config_path=str(self.config_file), defaults_path=str(self.defaults_file)
            )

            # log_level should come from User Config (overriding Default)
            self.assertEqual(manager.get_system_settings().log_level, "DEBUG")

            # default_model should come from Environment (overriding User Config)
            self.assertEqual(
                manager.get_model_settings().default_model, "deepseek-coder"
            )
        finally:
            del os.environ["FORGE_MODEL"]

    def test_github_token_environment_override(self) -> None:
        """FORGE_GITHUB_TOKEN should override any github_token set in the config file,
        keeping the secret out of forge.json in deployed/CI environments."""
        user_config = {"git": {"github_token": "file-based-token"}}
        self.config_file.write_text(json.dumps(user_config), encoding="utf-8")

        os.environ["FORGE_GITHUB_TOKEN"] = "env-based-token"

        try:
            manager = ConfigurationManager(
                config_path=str(self.config_file), defaults_path=str(self.defaults_file)
            )
            self.assertEqual(
                manager.get_full_config().git["github_token"], "env-based-token"
            )
        finally:
            del os.environ["FORGE_GITHUB_TOKEN"]

    def test_request_timeout_environment_override(self) -> None:
        """FORGE_REQUEST_TIMEOUT should override models.request_timeout, letting
        users tune the LLM HTTP timeout for their own hardware without editing JSON."""
        os.environ["FORGE_REQUEST_TIMEOUT"] = "45.5"

        try:
            manager = ConfigurationManager(
                config_path=str(self.config_file), defaults_path=str(self.defaults_file)
            )
            self.assertEqual(manager.get_model_settings().request_timeout, 45.5)
        finally:
            del os.environ["FORGE_REQUEST_TIMEOUT"]

    def test_save_configuration_public_api(self) -> None:
        """Issue 1 & 2: Tests saving via public API and standardized backup naming."""
        self.config_file.write_text("{}", encoding="utf-8")
        manager = ConfigurationManager(
            config_path=str(self.config_file), defaults_path=str(self.defaults_file)
        )

        # 1. Update using the new public API (no direct attribute modification)
        current_system = manager.get_system_settings()
        new_system = replace(current_system, log_level="WARNING")
        new_config = replace(manager.get_full_config(), system=new_system)

        manager.update_configuration(new_config)
        manager.save_configuration()

        # 2. Verify Backup Naming standard (forge.dev.json -> forge.dev.json.bak)
        expected_backup = Path(self.test_dir.name) / "forge.dev.json.bak"
        self.assertTrue(
            expected_backup.exists(),
            "Backup file was not created with correct extension.",
        )

    @patch("pathlib.Path.write_text")
    def test_permission_denied_on_save(self, mock_write: Any) -> None:
        """Issue 6: Tests that write failures raise a ConfigurationLoadError."""
        mock_write.side_effect = PermissionError("Read-only file system")

        manager = ConfigurationManager(
            config_path=str(self.config_file), defaults_path=str(self.defaults_file)
        )

        with self.assertRaises(ConfigurationLoadError):
            manager.save_configuration()


if __name__ == "__main__":
    unittest.main()
