"""Keyboard mapping helpers for review actions."""

from __future__ import annotations

from src.review.models import ReviewAction


def map_key_to_action(key: str) -> ReviewAction | None:
    """Map raw key input to a normalized review action."""
    normalized = key.lower().strip()
    if normalized in {"k", " ", "enter"}:
        return "keep"
    if normalized in {"r"}:
        return "reject"
    if normalized in {"s"}:
        return "skip"
    if normalized in {"b", "left", "up"}:
        return "back"
    if normalized in {"n", "right", "down"}:
        return "next"
    if normalized in {"q", "esc", "escape"}:
        return "quit"
    return None
