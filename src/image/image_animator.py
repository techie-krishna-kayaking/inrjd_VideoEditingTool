"""Animation selection utilities for slideshow clips."""

from __future__ import annotations

import random
from dataclasses import dataclass


ANIMATIONS = (
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "diagonal",
)


@dataclass(slots=True)
class AnimationOptions:
    """Animation controls for slideshow generation."""

    enabled: bool = True
    random_per_image: bool = True
    allowed: tuple[str, ...] = ANIMATIONS
    random_mode: bool = True
    default_animation: str = "zoom_in"
    zoom_min: float = 1.02
    zoom_max: float = 1.12


class ImageAnimator:
    """Choose animation descriptors while avoiding immediate repetition."""

    def __init__(self, random_seed: int | None = None) -> None:
        """Create animator with optional deterministic randomness."""
        self._rng = random.Random(random_seed)
        self._last_animation: str | None = None

    def choose(self, options: AnimationOptions) -> dict[str, float | str]:
        """Choose one animation for current image clip."""
        if not options.enabled:
            return {"name": "none", "zoom": 1.0}

        allowed = [name for name in options.allowed if name in ANIMATIONS]
        if not allowed:
            allowed = [options.default_animation if options.default_animation in ANIMATIONS else "zoom_in"]

        if not options.random_per_image and self._last_animation in allowed:
            name = self._last_animation
        else:
            candidates = [name for name in allowed if name != self._last_animation]
            if not candidates:
                candidates = allowed
            name = self._rng.choice(candidates)

        self._last_animation = name
        zoom = self._rng.uniform(options.zoom_min, options.zoom_max)
        return {"name": name, "zoom": round(zoom, 4)}
