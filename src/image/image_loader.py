"""Image discovery and ordering helpers for slideshow workflows."""

from __future__ import annotations

import random
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff"}


class ImageLoader:
    """Load and order image paths with deterministic shuffle support."""

    def __init__(self, random_seed: int | None = None) -> None:
        """Initialize loader with optional deterministic random seed."""
        self._rng = random.Random(random_seed)

    def load_paths(self, image_paths: list[str | Path]) -> list[Path]:
        """Normalize user-provided list to supported image paths only."""
        normalized: list[Path] = []
        for raw in image_paths:
            path = Path(raw)
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                normalized.append(path)
        return normalized

    def order_paths(self, paths: list[Path], order_mode: str) -> list[Path]:
        """Order paths using one of original, random, or chronological modes."""
        mode = order_mode.strip().lower()
        if mode == "original":
            return list(paths)
        if mode == "random":
            shuffled = list(paths)
            self._rng.shuffle(shuffled)
            return shuffled
        if mode == "chronological":
            return sorted(paths, key=_safe_mtime)
        raise ValueError(f"Unsupported image order mode: {order_mode}")


def _safe_mtime(path: Path) -> float:
    """Return modification time for sorting, defaulting to zero on failure."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
