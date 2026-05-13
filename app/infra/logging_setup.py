"""Structured JSON logging configuration for all processes (API + workers).

Call configure_logging() once at process startup before any log calls.
"""

import logging
import sys
from pathlib import Path

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog to emit JSON to stdout and logs/app.log.

    Every log line includes: timestamp, level, event, and any bound
    context vars (e.g. request_id carried from API through to workers).

    Args:
        log_level: Minimum log level string — DEBUG, INFO, WARNING, ERROR.
    """
    Path("logs").mkdir(exist_ok=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        # add_logger_name is omitted — it requires a stdlib Logger (.name attr),
        # but we use PrintLoggerFactory which produces a PrintLogger without .name.
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, etc.) through structlog
    file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
    stream_handler = logging.StreamHandler(sys.stdout)

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        handlers=[file_handler, stream_handler],
        force=True,
    )
