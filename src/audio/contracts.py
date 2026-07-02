"""Audio service contracts."""

from __future__ import annotations

from typing import Protocol


class AudioService(Protocol):
    """Contract for audio processing services."""

    def prepare_track(self, input_path: str) -> str:
        """Prepare an audio track path for downstream usage."""
