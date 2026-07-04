"""Custom exceptions for the ForgeAI Configuration module."""

class ConfigurationError(Exception):
    """Base exception for all configuration-related errors."""
    pass

class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration data fails schema, logic validation, or JSON parsing."""
    pass

class ConfigurationLoadError(ConfigurationError):
    """Raised when the configuration file cannot be read or parsed."""
    pass

class ConfigurationFileNotFound(ConfigurationLoadError):
    """Raised specifically when a required configuration file (like defaults.json) is missing."""
    pass