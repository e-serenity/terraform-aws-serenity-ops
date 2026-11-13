from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

from app.core.utils.redaction import redact_data, redact_secrets


class JsonFormatter(logging.Formatter):
    """Formats LogRecords as structured JSON lines for CloudWatch, ECS, and Datadog with automatic secret scrubbing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }

        # Include standard exception traceback if present (scrubbed)
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))

        # Include custom extra fields if provided (recursively scrubbed)
        for key, val in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and key not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName"
            ):
                payload[key] = redact_data(val)

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configures root logging with the JsonFormatter writing to sys.stdout."""
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not any(isinstance(h.formatter, JsonFormatter) for h in root_logger.handlers):
        root_logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Returns a namespaced logger for serenity-ops modules."""
    return logging.getLogger(f"serenity.{name}")


def log_message(
    message: str,
    extra: dict[str, Any] | None = None,
    level: str = "INFO",
    name: str = "serenity-ops",
) -> None:
    """Direct helper to log a message with optional structured metadata."""
    log_func = getattr(logging.getLogger(name), level.lower(), logging.info)
    if extra:
        log_func(message, extra=extra)
    else:
        log_func(message)
