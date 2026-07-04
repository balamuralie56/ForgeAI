"""
Core implementation of the non-blocking Logging Engine.
"""
import logging
import queue
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

from forge_core.configuration.service import ConfigurationService
from .formatters import ConsoleFormatter, JSONLinesFormatter
from .service import LoggingService


class BoundLogger(LoggingService):
    """
    Concrete implementation of the LoggingService interface.
    Wraps a standard Python logger and manages contextual data injection.
    """

    def __init__(self, logger: logging.Logger, context: Dict[str, Any]) -> None:
        self._logger = logger
        self._context = context

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._logger.debug(msg, extra={"forge_context": {**self._context, **kwargs}})

    def info(self, msg: str, **kwargs: Any) -> None:
        self._logger.info(msg, extra={"forge_context": {**self._context, **kwargs}})

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._logger.warning(msg, extra={"forge_context": {**self._context, **kwargs}})

    def error(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        self._logger.error(msg, exc_info=exc_info, extra={"forge_context": {**self._context, **kwargs}})

    def critical(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        self._logger.critical(msg, exc_info=exc_info, extra={"forge_context": {**self._context, **kwargs}})

    def get_logger(self, module_name: str) -> 'LoggingService':
        child_logger = self._logger.getChild(module_name)
        return BoundLogger(child_logger, self._context.copy())

    def bind_context(self, **kwargs: Any) -> 'LoggingService':
        new_context = {**self._context, **kwargs}
        return BoundLogger(self._logger, new_context)


class LoggingEngine:
    """
    Manages the lifecycle of the asynchronous logging system.
    Initializes sinks, handles rotation, and manages the background writer thread.
    """

    def __init__(self, config_service: ConfigurationService) -> None:
        """
        Initializes the Logging Engine using provided configuration.
        
        Args:
            config_service (ConfigurationService): The read-only configuration provider.
        """
        self.config = config_service.get_system_settings()
        self.log_dir = Path(self.config.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.root_logger = logging.getLogger("ForgeAI")
        self.root_logger.setLevel(self.config.log_level.upper())
        # Clear existing handlers to prevent duplicate logs on reloads
        self.root_logger.handlers.clear()
        
        # Setup the non-blocking queue
        self.log_queue: queue.Queue = queue.Queue(-1)
        self.queue_handler = QueueHandler(self.log_queue)
        self.root_logger.addHandler(self.queue_handler)

        self._listener = self._build_queue_listener()
        self._listener.start()

    def _build_queue_listener(self) -> QueueListener:
        """Constructs the sinks and binds them to the queue listener."""
        # 1. Console Sink
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ConsoleFormatter())

        # 2. File Sink (10 MB rotation, keep 5 backups)
        file_path = self.log_dir / "forge.log"
        file_handler = RotatingFileHandler(
            filename=str(file_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(JSONLinesFormatter())

        # The listener runs on a background thread consuming the queue
        return QueueListener(self.log_queue, console_handler, file_handler, respect_handler_level=True)

    def get_root_logger(self) -> LoggingService:
        """
        Provides the top-level bound logger interface.
        
        Returns:
            LoggingService: The root logger for ForgeAI.
        """
        return BoundLogger(self.root_logger, {})

    def shutdown(self) -> None:
        """
        Gracefully shuts down the background logging thread.
        Must be called by the Kernel during application termination.
        """
        self._listener.stop()
        logging.shutdown()