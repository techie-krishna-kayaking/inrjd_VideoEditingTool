"""Lazy metadata extraction and quality scoring for review items."""

from __future__ import annotations

from pathlib import Path

import cv2
from PIL import Image, UnidentifiedImageError

from src.review.models import MediaType, Orientation


def read_media_dimensions(path: Path, media_type: MediaType) -> tuple[int | None, int | None]:
    """Read width/height lazily from file based on media type."""
    if media_type == "image":
        try:
            with Image.open(path) as image:
                width, height = image.size
                return int(width), int(height)
        except (UnidentifiedImageError, OSError):
            return None, None

    if media_type == "video":
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            return None, None
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        capture.release()
        return width, height

    return None, None


def orientation_from_dimensions(width: int | None, height: int | None) -> Orientation:
    """Infer orientation from dimensions."""
    if width is None or height is None:
        return "unknown"
    if height >= width:
        return "portrait"
    return "landscape"


def estimate_quality_score(width: int | None, height: int | None, size_bytes: int) -> int:
    """Estimate quality score from dimensions and file size."""
    if width is None or height is None:
        return 0

    pixels = width * height
    baseline_pixels = 1920 * 1080
    pixel_component = min(80.0, (pixels / baseline_pixels) * 80.0)

    size_mb = size_bytes / (1024 * 1024)
    size_component = min(20.0, size_mb * 2.5)

    score = int(round(pixel_component + size_component))
    if score < 0:
        return 0
    if score > 100:
        return 100
    return score
