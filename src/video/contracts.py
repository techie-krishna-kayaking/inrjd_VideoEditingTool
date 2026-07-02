"""Video service contracts."""

from __future__ import annotations

from typing import Protocol


class VideoService(Protocol):
    """Contract for video processing services."""

    def validate_video(self, file_path: str) -> bool:
        """Validate whether a video file is acceptable for pipeline usage."""
