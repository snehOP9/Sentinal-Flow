"""Structured application logging without changing the host server's log policy."""

from __future__ import annotations

import logging

from pythonjsonlogger.json import JsonFormatter


def configure_structured_logging(level: str) -> None:
    """Attach one JSON handler to SentinelFlow logs, idempotently."""
    logger = logging.getLogger("sentinelflow")
    logger.setLevel(level.upper())
    if any(getattr(handler, "_sentinelflow_json", False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler._sentinelflow_json = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
