"""
Log formatters for the ForgeAI Logging Engine.
Provides specialized formatters for human-readable console output and machine-readable JSON files.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict


class ConsoleFormatter(logging.Formatter):
    """Formats log records for human-readable console output."""
    
    def __init__(self) -> None:
        super().__init__(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    def format(self, record: logging.LogRecord) -> str:
        """
        Applies standard formatting and appends bound context variables if they exist.
        
        Args:
            record (logging.LogRecord): The log record to format.
            
        Returns:
            str: The formatted log string.
        """
        formatted = super().format(record)
        context = getattr(record, "forge_context", None)
        if context:
            context_str = " ".join(f"{k}={v}" for k, v in context.items())
            formatted = f"{formatted} | Context: {{{context_str}}}"
        return formatted


class JSONLinesFormatter(logging.Formatter):
    """Formats log records as Newline Delimited JSON (NDJSON) for file persistence."""
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Converts the log record into a structured JSON string.
        
        Args:
            record (logging.LogRecord): The log record to format.
            
        Returns:
            str: A single-line JSON string representing the log event.
        """
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # Inject context variables if they exist
        context = getattr(record, "forge_context", None)
        if context:
            payload.update(context)

        # Inject traceback if an exception occurred
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(',', ':'))