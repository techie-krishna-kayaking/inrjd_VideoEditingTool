"""Service contracts for analyzer domain."""

from __future__ import annotations

from typing import Protocol

from src.models.entities import MediaFile


class AnalyzerService(Protocol):
    """Contract for analyzer implementations."""

    def collect_media(self, source_directory: str) -> list[MediaFile]:
        """Collect media descriptors from a source directory."""
