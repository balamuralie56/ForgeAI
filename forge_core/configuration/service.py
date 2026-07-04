"""
Service interfaces for configuration management.
Plugins and system modules should depend on these interfaces, not concrete implementations.
"""
from abc import ABC, abstractmethod

from .models import ForgeConfig, ModelSettings, PluginSettings, SystemSettings


class ConfigurationService(ABC):
    """Interface for accessing and updating configuration settings safely."""
    
    @abstractmethod
    def get_system_settings(self) -> SystemSettings:
        """Returns the current system settings."""
        pass

    @abstractmethod
    def get_model_settings(self) -> ModelSettings:
        """Returns the current model routing settings."""
        pass

    @abstractmethod
    def get_plugin_settings(self) -> PluginSettings:
        """Returns the current plugin configuration."""
        pass
        
    @abstractmethod
    def get_full_config(self) -> ForgeConfig:
        """Returns the aggregated root configuration object."""
        pass

    @abstractmethod
    def update_configuration(self, config: ForgeConfig) -> None:
        """
        Safely replaces the current active configuration.
        
        Args:
            config (ForgeConfig): The new immutable configuration object.
        """
        pass