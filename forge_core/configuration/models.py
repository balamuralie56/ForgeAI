"""
Data models for the ForgeAI configuration system.
"""

from dataclasses import dataclass, field
from typing import List
from .exceptions import ConfigurationValidationError


@dataclass(frozen=True)
class SystemSettings:
    workspace_dir: str = "forge_workspace"
    log_dir: str = "forge_data/logs"
    log_level: str = "INFO"
    coverage_threshold: float = 90.0

    def __post_init__(self) -> None:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_levels:
            raise ConfigurationValidationError(
                f"Invalid log_level: {self.log_level}. Must be one of {valid_levels}"
            )
        if not (0.0 <= self.coverage_threshold <= 100.0):
            raise ConfigurationValidationError(
                f"Coverage threshold must be between 0.0 and 100.0. Got: {self.coverage_threshold}"
            )


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    default_model: str
    base_url: str
    temperature: float
    max_tokens: int

    def __post_init__(self) -> None:
        if not (0.0 <= self.temperature <= 2.0):
            raise ConfigurationValidationError(
                f"Temperature must be between 0.0 and 2.0. Got: {self.temperature}"
            )
        if type(self.max_tokens) is not int or self.max_tokens <= 0:
            raise ConfigurationValidationError(
                f"max_tokens must be a positive integer. Got: {self.max_tokens}"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigurationValidationError(
                "base_url must include http:// or https://"
            )


@dataclass(frozen=True)
class PluginSettings:
    plugin_dir: str = "forge_plugins"
    enabled_plugins: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ForgeConfig:
    version: str = "1.0"
    schema_version: str = "1.0"
    system: SystemSettings = field(default_factory=SystemSettings)
    models: ModelSettings = None  # type: ignore # Instantiated via defaults.json
    plugins: PluginSettings = field(default_factory=PluginSettings)
