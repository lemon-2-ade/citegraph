"""Structured logging.

All log lines are emitted through structlog. Context variables (``request_id``,
``job_id``) are bound per request / per ingestion job and appear on every line.
A redaction processor strips values of keys that look like secrets.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO

import structlog

_SENSITIVE_KEY_PARTS = ("password", "secret", "token", "api_key", "apikey", "authorization")


def _redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
            event_dict[key] = "***"
    return event_dict


class _LazyStream:
    """Resolves ``sys.stdout``/``sys.stderr`` at write time.

    Binding the stream object at configuration time breaks when it is later replaced
    (test runners, CLI capture), so writes go to whatever the stream is *now*.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def write(self, data: str) -> int:
        stream: TextIO = getattr(sys, self._name)
        return stream.write(data)

    def flush(self) -> None:
        getattr(sys, self._name).flush()


def configure_logging(level: str = "INFO", json: bool = True, *, stream: str = "stdout") -> None:
    """Configure structlog. ``stream`` is ``"stdout"`` (services) or ``"stderr"`` (CLI)."""
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=_LazyStream(stream)),  # type: ignore[arg-type]
        cache_logger_on_first_use=False,
    )
    # Route stdlib logging (uvicorn, neo4j driver, httpx) through the same level.
    logging.basicConfig(
        level=level.upper(),
        stream=_LazyStream(stream),  # type: ignore[arg-type]
        format="%(message)s",
        force=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
