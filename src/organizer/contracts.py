"""Service contracts for organizer domain."""

from __future__ import annotations

from typing import Protocol

from src.models.entities import MediaFile


class OrganizerService(Protocol):
    """Contract for organizer implementations."""

    def organize(self, media_files: list[MediaFile], destination_root: str) -> None:
        """Organize media files into destination structure."""
