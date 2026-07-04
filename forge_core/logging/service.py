"""
Service interfaces for the ForgeAI Logging Engine.
Plugins and core modules should depend on this interface, not the concrete logger.
"""
from typing import Any, Protocol


class LoggingService(Protocol):
    """
    Standardized logging interface for ForgeAI.
    Ensures all modules and plugins can log asynchronously without knowing the underlying implementation.
    """

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log a debugging message."""
        ...

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log an informational message."""
        ...

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log a warning message."""
        ...

    def error(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log an error message. Set exc_info=True to include stack traces."""
        ...

    def critical(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log a critical system failure."""
        ...

    def get_logger(self, module_name: str) -> 'LoggingService':
        """
        Creates a child logger bound to a specific module or plugin name.
        
        Args:
            module_name (str): The name of the module (e.g., 'PlannerPlugin').
            
        Returns:
            LoggingService: A new logger instance scoped to the module.
        """
        ...

    def bind_context(self, **kwargs: Any) -> 'LoggingService':
        """
        Binds contextual data (like task_id) to all subsequent logs from this instance.
        
        Returns:
            LoggingService: The context-bound logger instance.
        """
        ...