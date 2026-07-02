"""Transition catalog contracts."""

from __future__ import annotations

from typing import Protocol


class TransitionCatalog(Protocol):
    """Contract for transition catalog providers."""

    def names(self) -> list[str]:
        """Return available transition names."""
