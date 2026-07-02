"""Image service contracts."""

from __future__ import annotations

from typing import Protocol


class ImageService(Protocol):
    """Contract for image processing services."""

    def validate_image(self, file_path: str) -> bool:
        """Validate whether an image file is acceptable for pipeline usage."""
