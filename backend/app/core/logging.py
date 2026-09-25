"""Structured logging configuration.

Every log line goes through structlog so request/session correlation ids
are attached consistently. Callers must never pass secrets, tokens, or full
conversation text into `logger.bind(...)` / log calls — see the
`sanitize_for_log` helper for the one place we intentionally redact.
"""
from __future__ import annotations

import logging
import sys

import structlog

_REDACT_KEYS = {"password", "token", "secret", "api_key", "authorization"}


def configure_logging(app_env: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_sensitive,
    ]
    if app_env == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _redact_sensitive(logger, method_name, event_dict):
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "***redacted***"
    return event_dict


def get_logger(**initial_context):
    return structlog.get_logger().bind(**initial_context)
