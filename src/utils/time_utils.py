"""Time utility functions."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(tz=timezone.utc)
