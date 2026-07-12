"""Timeline object generation for image-only slideshow clips."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TimelineClip:
    """Single image clip entry in slideshow timeline."""

    image_path: Path
    duration: float
    animation: dict[str, float | str]
    effects: dict[str, float]
    transition: str


@dataclass(slots=True)
class Timeline:
    """Full slideshow timeline object."""

    clips: list[TimelineClip] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        """Return accumulated clip duration."""
        return sum(clip.duration for clip in self.clips)


@dataclass(slots=True)
class DurationOptions:
    """Duration controls for slideshow clips."""

    image_duration: float = 1.5
    random_duration: bool = False
    minimum: float = 1.2
    maximum: float = 2.2
    duration_choices: tuple[float, ...] | None = None


class TimelineBuilder:
    """Build timeline objects independent of rendering command generation."""

    def __init__(self, random_seed: int | None = None) -> None:
        """Initialize with deterministic randomness support."""
        self._rng = random.Random(random_seed)

    def build(
        self,
        image_paths: list[Path],
        target_duration: float,
        duration_options: DurationOptions,
        transition_type: str,
        animations: list[dict[str, float | str]],
        effects: dict[str, float],
    ) -> Timeline:
        """Generate timeline clips up to target duration."""
        if not image_paths:
            return Timeline(clips=[])

        clips: list[TimelineClip] = []
        cursor = 0.0
        index = 0
        total_images = len(image_paths)

        while cursor < target_duration and total_images > 0:
            image_path = image_paths[index % total_images]
            animation = animations[index % len(animations)] if animations else {"name": "none", "zoom": 1.0}
            duration = _pick_duration(duration_options=duration_options, rng=self._rng)

            remaining = target_duration - cursor
            if duration > remaining:
                duration = max(0.1, remaining)

            clips.append(
                TimelineClip(
                    image_path=image_path,
                    duration=round(duration, 4),
                    animation=animation,
                    effects=effects,
                    transition=transition_type,
                )
            )
            cursor += duration
            index += 1

        return Timeline(clips=clips)


def _pick_duration(duration_options: DurationOptions, rng: random.Random) -> float:
    """Pick clip duration from fixed or random range."""
    if duration_options.random_duration:
        if duration_options.duration_choices:
            choices = [max(0.1, float(item)) for item in duration_options.duration_choices]
            if choices:
                return rng.choice(choices)
        minimum = max(0.1, duration_options.minimum)
        maximum = max(minimum, duration_options.maximum)
        return rng.uniform(minimum, maximum)
    return max(0.1, duration_options.image_duration)
