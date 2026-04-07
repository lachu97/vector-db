# vectordb/logging_config.py
"""
Structlog configuration for Vector DB.

Call configure_logging() once at app startup (before any loggers are used).

LOG_FORMAT env var controls the output:
  - "json"    → machine-readable JSON (default, production)
  - "console" → human-readable coloured output (development)
"""
import logging
import sys

import structlog


def configure_logging(log_format: str = "json", log_level: str = "INFO") -> None:
    """Configure structlog and stdlib logging to use the same pipeline."""

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors for both structlog-native and stdlib-wrapped records
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    if log_format == "console":
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so third-party libraries (uvicorn, sqlalchemy)
    # produce output at the right level.
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout,
    )
    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
