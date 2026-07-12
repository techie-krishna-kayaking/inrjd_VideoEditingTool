"""Lazy metadata extraction and quality scoring for review items."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
from PIL import Image, ImageOps, UnidentifiedImageError

from src.review.models import MediaType, Orientation


def read_media_dimensions(path: Path, media_type: MediaType) -> tuple[int | None, int | None]:
    """Read width/height lazily from file based on media type."""
    if media_type == "image":
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened)
                width, height = image.size
                return int(width), int(height)
        except (UnidentifiedImageError, OSError):
            return None, None

    if media_type == "video":
        # Prefer ffprobe for display orientation (handles rotation metadata).
        probed = _video_dimensions_with_rotation(path)
        if probed != (None, None):
            return probed

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
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "unknown"


def _video_dimensions_with_rotation(path: Path) -> tuple[int | None, int | None]:
    """Read video dimensions and apply metadata rotation when available."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return None, None
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        return None, None

    streams = payload.get("streams")
    if not isinstance(streams, list):
        return None, None

    stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), None)
    if not isinstance(stream, dict):
        return None, None

    width = int(stream.get("width", 0) or 0)
    height = int(stream.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        return None, None

    rotation = _read_rotation(stream)
    if rotation in {90, 270}:
        width, height = height, width
    return width, height


def _read_rotation(video_stream: dict) -> int:
    """Extract normalized rotation from ffprobe stream payload."""
    tags = video_stream.get("tags") if isinstance(video_stream.get("tags"), dict) else {}
    side_data = video_stream.get("side_data_list") if isinstance(video_stream.get("side_data_list"), list) else []

    values: list[int] = []
    raw_tag = tags.get("rotate")
    if raw_tag is not None:
        try:
            values.append(int(float(str(raw_tag).strip())))
        except Exception:
            pass

    for item in side_data:
        if not isinstance(item, dict):
            continue
        raw_side = item.get("rotation")
        if raw_side is None:
            continue
        try:
            values.append(int(float(str(raw_side).strip())))
        except Exception:
            continue

    if not values:
        return 0

    value = values[-1] % 360
    if value < 0:
        value += 360
    return value


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
