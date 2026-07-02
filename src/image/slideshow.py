"""Reusable slideshow engine for cinematic image timeline generation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.image.image_animator import AnimationOptions, ImageAnimator
from src.image.image_effects import ColorEffectOptions
from src.image.image_loader import ImageLoader
from src.image.image_processor import ImageProcessor, ProcessorOptions
from src.image.image_validator import ImageValidator, ValidationOptions
from src.image.timeline_builder import DurationOptions, Timeline, TimelineBuilder


@dataclass(slots=True)
class SlideshowOptions:
    """Input and behavior configuration for slideshow generation."""

    target_duration: float
    target_width: int
    target_height: int
    transition_type: str = "cross_dissolve"
    image_order: str = "original"
    fit_mode: str = "center_crop"
    safe_area_ratio: float = 0.9


@dataclass(slots=True)
class SlideshowBuildResult:
    """Result object containing timeline and preprocessing diagnostics."""

    timeline: Timeline
    loaded_images: int
    skipped_images: int
    skipped_reasons: list[tuple[Path, str]]
    processing_seconds: float


class SlideshowEngine:
    """Convert image lists into timeline objects independent of video profile."""

    def __init__(
        self,
        cache_dir: Path,
        random_seed: int | None = None,
    ) -> None:
        """Create engine and reusable sub-components."""
        self._loader = ImageLoader(random_seed=random_seed)
        self._validator = ImageValidator()
        self._processor = ImageProcessor(cache_dir=cache_dir)
        self._animator = ImageAnimator(random_seed=random_seed)
        self._timeline_builder = TimelineBuilder(random_seed=random_seed)

    def build(
        self,
        image_paths: list[str | Path],
        options: SlideshowOptions,
        validation_options: ValidationOptions,
        duration_options: DurationOptions,
        animation_options: AnimationOptions,
        color_options: ColorEffectOptions,
    ) -> SlideshowBuildResult:
        """Build slideshow timeline from source images."""
        started = time.perf_counter()

        loaded = self._loader.load_paths(image_paths)
        ordered = self._loader.order_paths(loaded, order_mode=options.image_order)
        validation = self._validator.validate(ordered, options=validation_options)

        logger.info("Slideshow: images_loaded={} images_skipped={}", len(validation.valid_paths), len(validation.skipped))

        processor_options = ProcessorOptions(
            width=options.target_width,
            height=options.target_height,
            fit_mode=options.fit_mode,
            safe_area_ratio=options.safe_area_ratio,
            cache_enabled=True,
        )

        processed_paths: list[Path] = []
        animations: list[dict[str, float | str]] = []

        for path in validation.valid_paths:
            processed = self._processor.process(path, processor_options=processor_options, color_options=color_options)
            processed_paths.append(processed)
            animation = self._animator.choose(animation_options)
            animations.append(animation)

        logger.info("Slideshow: animations_applied={}", len(animations))

        effects = {
            "brightness": color_options.brightness,
            "contrast": color_options.contrast,
            "saturation": color_options.saturation,
            "gamma": color_options.gamma,
            "sharpen": color_options.sharpen,
        }

        timeline = self._timeline_builder.build(
            image_paths=processed_paths,
            target_duration=options.target_duration,
            duration_options=duration_options,
            transition_type=options.transition_type,
            animations=animations,
            effects=effects,
        )

        elapsed = time.perf_counter() - started
        logger.info("Slideshow: processing_time_seconds={:.3f}", elapsed)

        return SlideshowBuildResult(
            timeline=timeline,
            loaded_images=len(validation.valid_paths),
            skipped_images=len(validation.skipped),
            skipped_reasons=validation.skipped,
            processing_seconds=elapsed,
        )
