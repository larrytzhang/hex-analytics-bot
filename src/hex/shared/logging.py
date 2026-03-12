"""Structured JSON logging configuration for the Hex Analytics Bot.

Provides a single configure_logging() function that sets up structured
JSON-formatted log output. Called once at startup from main.py.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Custom log formatter that outputs structured JSON lines.

    Each log record is serialized as a single JSON object with
    timestamp, level, module, message, and optional extra fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            JSON string with timestamp, level, module, message, and
            any extra data attached to the record.
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields passed via the `extra` kwarg
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        return json.dumps(log_entry, default=str)


def configure_logging(level: str | None = None) -> None:
    """Configure structured JSON logging for the application.

    Sets up the root logger with a JSON formatter writing to stdout.
    Reads LOG_LEVEL from environment if no level is explicitly provided.

    Args:
        level: Optional log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to the LOG_LEVEL environment variable, or INFO if unset.
    """
    log_level = level or os.environ.get("LOG_LEVEL", "INFO")

    # Create handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
