"""Validation utilities for slideshow image inputs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


@dataclass(slots=True)
class ValidationOptions:
    """Validation knobs for slideshow image selection."""

    min_width: int = 640
    min_height: int = 640
    skip_duplicates: bool = True


@dataclass(slots=True)
class ValidationResult:
    """Result of image validation pass."""

    valid_paths: list[Path]
    skipped: list[tuple[Path, str]]


class ImageValidator:
    """Validate readability, dimensions, and duplicate signatures."""

    def validate(self, image_paths: list[Path], options: ValidationOptions) -> ValidationResult:
        """Validate input images and return valid paths with skip reasons."""
        valid_paths: list[Path] = []
        skipped: list[tuple[Path, str]] = []
        seen_signatures: set[str] = set()

        for path in image_paths:
            if not path.exists() or not path.is_file():
                skipped.append((path, "missing"))
                continue

            dimensions = _safe_dimensions(path)
            if dimensions is None:
                skipped.append((path, "corrupted_or_unreadable"))
                continue

            width, height = dimensions
            if width < options.min_width or height < options.min_height:
                skipped.append((path, "tiny"))
                continue

            if options.skip_duplicates:
                signature = _file_signature(path)
                if signature in seen_signatures:
                    skipped.append((path, "duplicate"))
                    continue
                seen_signatures.add(signature)

            valid_paths.append(path)

        return ValidationResult(valid_paths=valid_paths, skipped=skipped)


def _safe_dimensions(path: Path) -> tuple[int, int] | None:
    """Return image dimensions when readable and valid."""
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            return int(width), int(height)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _file_signature(path: Path) -> str:
    """Build duplicate signature from file size and sampled bytes."""
    stat = path.stat()
    digest = hashlib.sha1()
    digest.update(str(stat.st_size).encode("utf-8"))
    with path.open("rb") as handle:
        first = handle.read(65536)
        digest.update(first)
        if stat.st_size > 65536:
            handle.seek(max(0, stat.st_size - 65536))
            digest.update(handle.read(65536))
    return digest.hexdigest()
