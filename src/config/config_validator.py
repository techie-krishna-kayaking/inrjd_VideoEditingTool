"""Validation layer for loaded application settings."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from src.config.config_models import OverlayItemSettings, ProfileSettings, Settings


class ConfigValidationError(Exception):
    """Raised when one or more config validation checks fail."""


SUPPORTED_ENCODERS = {"auto", "cpu", "nvidia", "videotoolbox", "quicksync", "amd"}
SUPPORTED_LOG_LEVELS = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
ALLOWED_RESOLUTIONS = {
    (1080, 1920),
    (1920, 1080),
    (720, 1280),
    (1280, 720),
    (2160, 3840),
    (3840, 2160),
}


def validate_settings(settings: Settings) -> None:
    """Validate settings object and raise friendly errors when invalid."""
    errors: list[str] = []

    _validate_required_sections(settings=settings, errors=errors)
    _validate_paths(settings=settings, errors=errors)
    _validate_render(settings=settings, errors=errors)
    _validate_profile(profile=settings.shorts, label="shorts", errors=errors)
    _validate_profile(profile=settings.long, label="long", errors=errors)
    _validate_numeric_ranges(settings=settings, errors=errors)
    _validate_assets(settings=settings, errors=errors)
    _validate_ffmpeg(settings=settings, errors=errors)
    _validate_logging(settings=settings, errors=errors)
    _validate_review(settings=settings, errors=errors)

    if errors:
        lines = ["Configuration validation failed:"] + [f"- {item}" for item in errors]
        raise ConfigValidationError("\n".join(lines))


def _validate_required_sections(settings: Settings, errors: list[str]) -> None:
    """Validate required project fields."""
    if not settings.project.name.strip():
        errors.append("Missing required field: project.name")
    if not settings.project.version.strip():
        errors.append("Missing required field: project.version")
    if not settings.project.author.strip():
        errors.append("Missing required field: project.author")


def _validate_paths(settings: Settings, errors: list[str]) -> None:
    """Validate core path values and existing critical directories."""
    path_values = {
        "paths.raw_data": settings.paths.raw_data,
        "paths.input": settings.paths.input,
        "paths.output": settings.paths.output,
        "paths.assets": settings.paths.assets,
        "paths.music": settings.paths.music,
        "paths.reports": settings.paths.reports,
        "paths.logs": settings.paths.logs,
        "paths.temp": settings.paths.temp,
    }
    for field_name, value in path_values.items():
        if not str(value).strip():
            errors.append(f"Invalid folder value: {field_name} cannot be empty")

    assets_dir = settings.project_root / settings.paths.assets
    if not assets_dir.exists() or not assets_dir.is_dir():
        errors.append(f"Missing assets folder: {assets_dir}")

    music_dir = settings.project_root / settings.paths.music
    if not music_dir.exists() or not music_dir.is_dir():
        errors.append(f"Missing music folder: {music_dir}")


def _validate_render(settings: Settings, errors: list[str]) -> None:
    """Validate render settings values and supported encoders."""
    if settings.render.workers <= 0:
        errors.append("Invalid workers value: render.workers must be positive")
    if settings.render.workers > 2:
        errors.append("Invalid workers value: render.workers cannot exceed 2")
    if settings.render.preferred_encoder not in SUPPORTED_ENCODERS:
        errors.append(
            f"Unsupported encoder: {settings.render.preferred_encoder}. "
            f"Supported: {', '.join(sorted(SUPPORTED_ENCODERS))}"
        )


def _validate_profile(profile: ProfileSettings, label: str, errors: list[str]) -> None:
    """Validate output profile resolution, fps, and duration constraints."""
    if profile.fps <= 0 or profile.fps > 120:
        errors.append(f"Invalid FPS for {label}: {profile.fps}")

    pair = (profile.resolution.width, profile.resolution.height)
    if pair not in ALLOWED_RESOLUTIONS:
        errors.append(
            f"Invalid resolution for {label}: {pair[0]}x{pair[1]} is not supported"
        )

    if profile.duration.minimum <= 0 or profile.duration.default <= 0 or profile.duration.maximum <= 0:
        errors.append(f"Invalid duration for {label}: duration values must be positive")
    if not (profile.duration.minimum <= profile.duration.default <= profile.duration.maximum):
        errors.append(
            f"Invalid duration for {label}: minimum <= default <= maximum must hold"
        )


def _validate_numeric_ranges(settings: Settings, errors: list[str]) -> None:
    """Validate non-profile numeric boundaries."""
    if settings.images.image_duration <= 0:
        errors.append("Invalid value: images.image_duration must be positive")
    if settings.images.avoid_recent_repeat < 0:
        errors.append("Invalid value: images.avoid_recent_repeat cannot be negative")

    if settings.videos.clip_duration.minimum <= 0 or settings.videos.clip_duration.maximum <= 0:
        errors.append("Invalid value: videos.clip_duration values must be positive")
    if settings.videos.clip_duration.minimum > settings.videos.clip_duration.maximum:
        errors.append("Invalid value: videos.clip_duration.minimum cannot exceed maximum")

    if not (0.0 <= settings.audio.music_volume <= 1.0):
        errors.append("Invalid value: audio.music_volume must be between 0 and 1")

    if settings.thumbnails.width <= 0 or settings.thumbnails.height <= 0:
        errors.append("Invalid thumbnail resolution: width and height must be positive")
    if settings.thumbnails.jpeg_quality < 1 or settings.thumbnails.jpeg_quality > 100:
        errors.append("Invalid JPEG quality: thumbnails.jpeg_quality must be in [1, 100]")


def _validate_assets(settings: Settings, errors: list[str]) -> None:
    """Validate required overlay assets when overlays are enabled."""
    for label, overlay in _iter_overlays(settings):
        if overlay.enabled:
            overlay_path = settings.project_root / overlay.file
            if not overlay_path.exists() or not overlay_path.is_file():
                errors.append(f"Missing overlay file for {label}: {overlay_path}")
            if not (0.0 <= overlay.opacity <= 1.0):
                errors.append(f"Invalid overlay opacity for {label}: must be between 0 and 1")



def _validate_ffmpeg(settings: Settings, errors: list[str]) -> None:
    """Validate ffmpeg availability using configured path or system PATH."""
    ffmpeg_program = settings.render.ffmpeg_path.strip() or "ffmpeg"
    ffprobe_program = "ffprobe"

    if shutil.which(ffmpeg_program) is None:
        errors.append(
            f"Missing FFmpeg: executable '{ffmpeg_program}' is not available on PATH"
        )
    if shutil.which(ffprobe_program) is None:
        errors.append("Missing FFprobe: executable 'ffprobe' is not available on PATH")


def _validate_logging(settings: Settings, errors: list[str]) -> None:
    """Validate logging level compatibility."""
    if settings.logging.level.upper() not in SUPPORTED_LOG_LEVELS:
        errors.append(
            f"Invalid logging level: {settings.logging.level}. "
            f"Supported: {', '.join(sorted(SUPPORTED_LOG_LEVELS))}"
        )


def _validate_review(settings: Settings, errors: list[str]) -> None:
    """Validate review engine settings values."""
    if settings.review.low_quality_threshold < 0 or settings.review.low_quality_threshold > 100:
        errors.append("Invalid value: review.low_quality_threshold must be in [0, 100]")

    if settings.review.estimated_seconds_per_item <= 0:
        errors.append("Invalid value: review.estimated_seconds_per_item must be positive")

    if not settings.review.progress_file.strip():
        errors.append("Invalid value: review.progress_file cannot be empty")

    if not settings.review.report_file.strip():
        errors.append("Invalid value: review.report_file cannot be empty")

    strategy = settings.organizer.copy_strategy.strip().lower()
    if strategy not in {"copy", "move", "link"}:
        errors.append("Invalid value: organizer.copy_strategy must be copy, move, or link")


def _iter_overlays(settings: Settings) -> Iterable[tuple[str, OverlayItemSettings]]:
    """Yield overlay items with labels."""
    yield "header", settings.overlays.header
    yield "footer", settings.overlays.footer
    yield "socials", settings.overlays.socials
    yield "website", settings.overlays.website
