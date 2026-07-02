"""Effect catalog contracts."""

from __future__ import annotations

from typing import Protocol


class EffectCatalog(Protocol):
    """Contract for effect catalog providers."""

    def names(self) -> list[str]:
        """Return available effect names."""
