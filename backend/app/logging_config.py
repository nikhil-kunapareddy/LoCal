"""Structured logging setup.

Emits one JSON object per line so logs are machine-parseable in any aggregator.
Extra fields passed via ``logger.info("event", extra={...})`` are merged into the
record. Call :func:`configure_logging` once at app startup.
"""

from __future__ import annotations

import json
import logging
from typing import Any

# Attributes present on every LogRecord; anything else is treated as a custom
# field added by the caller via ``extra=``.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
