"""Structured logging with secret redaction.

Principles:
- Logs are JSON lines (one object per line) so they can be shipped/grepped.
- **No payload data**: pipeline logs carry identifiers, counts and statuses —
  never transaction descriptions or amounts.
- Secrets are redacted defensively: even if a token reaches a log call, the
  formatter strips known secret shapes and configured secret values.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Shapes of common credentials, redacted wherever they appear in a message.
_SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot tokens
    re.compile(r"(?i)\b(app[- ]?password|password|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
]

_REDACTED = "***REDACTED***"


def sanitize(message: str, extra_secrets: list[str] | None = None) -> str:
    """Remove credential-shaped substrings and any caller-supplied secrets."""
    out = message
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(secret, _REDACTED)
    return out


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def __init__(self, extra_secrets: list[str] | None = None) -> None:
        super().__init__()
        self._extra_secrets = extra_secrets or []

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": sanitize(record.getMessage(), self._extra_secrets),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure the root logger once for the whole application."""
    root = logging.getLogger()
    # Idempotent: replace our own handler configuration if called twice.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(level.upper())
    formatter: logging.Formatter = JsonFormatter()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Namespaced logger for a FinFlow component."""
    return logging.getLogger(f"finflow.{name}")
