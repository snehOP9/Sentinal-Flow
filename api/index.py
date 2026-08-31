"""Vercel entrypoint for the existing SentinelFlow FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_SOURCE = Path(__file__).resolve().parents[1] / "backend" / "src"
if str(BACKEND_SOURCE) not in sys.path:
    sys.path.insert(0, str(BACKEND_SOURCE))

from fraud_platform.main import app  # noqa: E402

__all__ = ["app"]
