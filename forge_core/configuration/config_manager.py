"""
Configuration Manager for ForgeAI.
Implements ConfigurationService and handles loading, validation, and serialization.
"""

import json
import logging
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from .exceptions import (
    ConfigurationFileNotFound,
    ConfigurationLoadError,
    ConfigurationValidationError,
)
from .models import ForgeConfig, ModelSettings, PluginSettings, SystemSettings
from .service import ConfigurationService

logger = logging.getLogger("ForgeAI.ConfigManager")


class ConfigurationManager(ConfigurationService):
    """
    Manages the lifecycle of the ForgeAI configuration.
    Kernel will instantiate this once and provide it as a ConfigurationService.
    """

    def __init__(
        self,
        config_path: str = "forge.json",
        defaults_path: str = "config/defaults.json",
    ) -> None:
        self.config_path: Path = Path(config_path)
        self.defaults_path: Path = Path(defaults_path)

        logger.info("Initializing ConfigurationManager...")

        # Atomic Initialization: The object never exists in an invalid state.
        self._config: ForgeConfig = self._build_configuration()

    def _build_configuration(self) -> ForgeConfig:
        """
        Pure function that reads files, merges defaults, applies environment overrides,
        and constructs the root configuration object without mutating class state.

        Returns:
            ForgeConfig: The fully validated and immutable configuration object.
        """
        defaults = self._load_json_file(self.defaults_path, is_required=True)
        user_data = (
            self._load_json_file(self.config_path, is_required=False)
            if self.config_path.exists()
            else {}
        )

        merged_data = self._merge_dicts(defaults, user_data)
        env_overridden_data = self._apply_environment_variables(merged_data)

        try:
            system_cfg = SystemSettings(**env_overridden_data.get("system", {}))
            models_cfg = ModelSettings(**env_overridden_data.get("models", {}))
            plugins_cfg = PluginSettings(**env_overridden_data.get("plugins", {}))

            return ForgeConfig(
                version=env_overridden_data.get("version", "1.0"),
                schema_version=env_overridden_data.get("schema_version", "1.0"),
                system=system_cfg,
                models=models_cfg,
                plugins=plugins_cfg,
                git=env_overridden_data.get("git", {}),
                security=env_overridden_data.get("security", {}),
                reviewer=env_overridden_data.get("reviewer", {}),
            )
        except TypeError as e:
            raise ConfigurationValidationError(f"Schema mismatch: {e}") from e

    def _load_json_file(self, path: Path, is_required: bool = False) -> Dict[str, Any]:
        """Safely loads and parses a JSON file using pathlib."""
        if not path.exists():
            if is_required:
                raise ConfigurationFileNotFound(
                    f"Required configuration file missing: {path}"
                )
            return {}

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON in {path}: {e}")
            raise ConfigurationValidationError(f"Failed to parse {path}: {e}") from e

    def _merge_dicts(self, default: Dict, user: Dict) -> Dict:
        """Deep merges user overrides into default settings."""
        merged = default.copy()
        for key, value in user.items():
            if (
                isinstance(value, dict)
                and key in merged
                and isinstance(merged[key], dict)
            ):
                merged[key] = self._merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _apply_environment_variables(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Applies FORGE_* environment variables over the configuration data."""
        if os.environ.get("FORGE_WORKSPACE"):
            data.setdefault("system", {})["workspace_dir"] = os.environ.get(
                "FORGE_WORKSPACE"
            )
        if os.environ.get("FORGE_LOG_LEVEL"):
            data.setdefault("system", {})["log_level"] = os.environ.get(
                "FORGE_LOG_LEVEL"
            )
        if os.environ.get("FORGE_MODEL"):
            data.setdefault("models", {})["default_model"] = os.environ.get(
                "FORGE_MODEL"
            )
        if os.environ.get("FORGE_REQUEST_TIMEOUT"):
            data.setdefault("models", {})["request_timeout"] = float(
                os.environ["FORGE_REQUEST_TIMEOUT"]
            )
        if os.environ.get("FORGE_GITHUB_TOKEN"):
            data.setdefault("git", {})["github_token"] = os.environ.get(
                "FORGE_GITHUB_TOKEN"
            )
        return data

    def save_configuration(self) -> None:
        """Saves current state to disk, creating a backup first."""
        if self.config_path.exists():
            backup_path = self.config_path.with_name(f"{self.config_path.name}.bak")
            try:
                shutil.copy2(self.config_path, backup_path)
            except IOError as e:
                logger.warning(f"Failed to create backup at {backup_path}: {e}")

        try:
            self.config_path.write_text(
                json.dumps(asdict(self._config), indent=4), encoding="utf-8"
            )
            logger.info(f"Configuration saved to {self.config_path}")
        except (IOError, PermissionError) as e:
            raise ConfigurationLoadError(f"Failed to write configuration: {e}") from e

    # --- ConfigurationService Implementation ---
    def get_system_settings(self) -> SystemSettings:
        return self._config.system

    def get_model_settings(self) -> ModelSettings:
        return self._config.models

    def get_plugin_settings(self) -> PluginSettings:
        return self._config.plugins

    def get_full_config(self) -> ForgeConfig:
        return self._config

    def update_configuration(self, config: ForgeConfig) -> None:
        self._config = config
