"""Configuration loading and typed model construction."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.config.config_models import (
    AdvancedSettings,
    AudioEngineSettings,
    ClipDurationSettings,
    ColorGradingSettings,
    DurationSettings,
    EnvironmentSettings,
    ImageSettings,
    LoggingSettings,
    MediaAnalyzerSettings,
    OrganizerSettings,
    OverlayItemSettings,
    OverlaySettings,
    PathSettings,
    ProfileSettings,
    ProjectSettings,
    RenderSettings,
    ReviewSettings,
    ReportSettings,
    Resolution,
    Settings,
    TextOverlaySettings,
    ThumbnailSettings,
    TransitionSettings,
    VideoSettings,
)


class ConfigLoadError(Exception):
    """Raised when configuration cannot be loaded from disk."""


DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "name": "ISKCON NRJD Media Engine",
        "version": "0.1.0",
        "author": "ISKCON NRJD Media Team",
        "organization": "ISKCON NRJD",
    },
    "paths": {
        "raw_data": "raw_data",
        "input": "input",
        "output": "output",
        "assets": "assets",
        "music": "assets/music",
        "reports": "work/reports",
        "logs": "work/logs",
        "temp": "work/temp",
    },
    "render": {
        "workers": 2,
        "gpu_auto_detect": True,
        "overwrite_existing": False,
        "resume_failed": True,
        "create_reports": True,
        "create_logs": True,
        "create_thumbnail": True,
        "preferred_encoder": "auto",
        "ffmpeg_path": "ffmpeg",
    },
    "shorts": {
        "enabled": True,
        "resolution": {"width": 1080, "height": 1920},
        "fps": 60,
        "duration": {"minimum": 30, "default": 60, "maximum": 90},
    },
    "long": {
        "enabled": True,
        "resolution": {"width": 1920, "height": 1080},
        "fps": 60,
        "duration": {"minimum": 240, "default": 360, "maximum": 540},
    },
    "images": {
        "random_order": True,
        "image_duration": 1.5,
        "reuse_images": True,
        "avoid_recent_repeat": 10,
        "enable_ken_burns": True,
        "animation_random": True,
    },
    "videos": {
        "clip_duration": {"minimum": 3, "maximum": 5},
        "shuffle": True,
        "mute_original_audio": True,
    },
    "transitions": {
        "hard_cut": True,
        "cross_dissolve": True,
        "film_burn": True,
        "morph_cut": True,
        "match_cut": True,
        "random_selection": True,
        "duration": 0.6,
    },
    "color_grading": {
        "brightness": 0.03,
        "contrast": 1.05,
        "saturation": 1.05,
        "sharpen": 0.2,
        "gamma": 1.0,
    },
    "audio": {
        "random_music": True,
        "random_start_position": True,
        "fade_in": 2.0,
        "fade_out": 2.0,
        "normalize_loudness": True,
        "music_volume": 0.24,
        "crossfade": 1.5,
    },
    "text_overlay": {
        "opening_title": "Hare Krishna",
        "animation": "fade",
        "tilt": 2.0,
        "glass_effect": True,
        "duration": 4.0,
        "font": "assets/fonts/default.ttf",
        "shadow": True,
        "outline": True,
    },
    "overlays": {
        "header": {
            "enabled": True,
            "file": "assets/overlays/shorts_header_footer.png",
            "opacity": 0.95,
            "margin_top": 16,
            "margin_bottom": 0,
            "margin_left": 16,
            "margin_right": 16,
        },
        "footer": {
            "enabled": False,
            "file": "assets/overlays/shorts_header_footer.png",
            "opacity": 0.95,
            "margin_top": 0,
            "margin_bottom": 16,
            "margin_left": 16,
            "margin_right": 16,
        },
        "socials": {
            "enabled": True,
            "file": "assets/overlays/socials.png",
            "opacity": 0.95,
            "margin_top": 0,
            "margin_bottom": 16,
            "margin_left": 16,
            "margin_right": 16,
        },
        "website": {
            "enabled": True,
            "file": "assets/overlays/website.png",
            "opacity": 0.95,
            "margin_top": 0,
            "margin_bottom": 16,
            "margin_left": 16,
            "margin_right": 16,
        },
    },
    "thumbnails": {"generate": True, "width": 1280, "height": 720, "jpeg_quality": 92},
    "media_analyzer": {
        "minimum_resolution": {"width": 720, "height": 720},
        "ignore_corrupted_files": True,
        "ignore_hidden_files": True,
        "supported_extensions": [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".mp4",
            ".mov",
            ".m4v",
            ".mkv",
        ],
    },
    "organizer": {
        "shortform_pictures": True,
        "shortform_videos": True,
        "longform_pictures": True,
        "longform_videos": True,
        "rejected": True,
        "copy_strategy": "copy",
        "analyzer_report": "output/reports/analyzer_report.json",
    },
    "review": {
        "open_with_default_viewer": True,
        "reviewer": "",
        "low_quality_threshold": 45,
        "estimated_seconds_per_item": 20.0,
        "progress_file": "review_progress.json",
        "report_file": "review_report.json",
    },
    "logging": {
        "console": True,
        "file": True,
        "level": "INFO",
        "rotation": "1 day",
        "retention": "14 days",
    },
    "reports": {"json": True, "csv": True, "summary": True, "statistics": True},
    "advanced": {
        "experimental_features": False,
        "dry_run": False,
        "debug_mode": False,
        "developer_mode": False,
    },
    "environment": {
        "dotenv_enabled": True,
        "output_folder_key": "NRJD_OUTPUT_FOLDER",
        "ffmpeg_path_key": "NRJD_FFMPEG_PATH",
        "workers_key": "NRJD_WORKERS",
        "debug_key": "NRJD_DEBUG",
    },
}

REQUIRED_TOP_LEVEL_SECTIONS: tuple[str, ...] = (
    "project",
    "paths",
    "render",
    "shorts",
    "long",
    "images",
    "videos",
    "transitions",
    "color_grading",
    "audio",
    "text_overlay",
    "overlays",
    "thumbnails",
    "media_analyzer",
    "organizer",
    "review",
    "logging",
    "reports",
    "advanced",
    "environment",
)


def load_yaml_file(config_path: Path) -> dict[str, Any]:
    """Load raw YAML as a dictionary from the given path."""
    if not config_path.exists() or not config_path.is_file():
        raise ConfigLoadError(f"Configuration file is missing: {config_path}")

    try:
        content = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Failed to parse YAML at {config_path}: {exc}") from exc

    if not isinstance(content, dict):
        raise ConfigLoadError("Configuration root must be a YAML mapping.")

    return content


def validate_required_sections(raw_config: Mapping[str, Any]) -> None:
    """Validate required top-level sections before applying defaults."""
    missing = [section for section in REQUIRED_TOP_LEVEL_SECTIONS if section not in raw_config]
    if missing:
        message = ", ".join(missing)
        raise ConfigLoadError(f"Missing required config sections: {message}")


def merge_with_defaults(user_config: Mapping[str, Any]) -> dict[str, Any]:
    """Merge user configuration on top of defaults recursively."""

    def _deep_merge(base: dict[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, Mapping):
                base[key] = _deep_merge(base[key], value)
            else:
                base[key] = copy.deepcopy(value)
        return base

    result = copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(result, user_config)


def apply_environment_overrides(config_data: dict[str, Any], env: Mapping[str, str] | None = None) -> None:
    """Apply environment overrides in-place using configured env keys."""
    env_map = env if env is not None else os.environ
    env_cfg = config_data["environment"]

    output_key = str(env_cfg["output_folder_key"])
    ffmpeg_key = str(env_cfg["ffmpeg_path_key"])
    workers_key = str(env_cfg["workers_key"])
    debug_key = str(env_cfg["debug_key"])

    if output_key in env_map and env_map[output_key].strip():
        config_data["paths"]["output"] = env_map[output_key].strip()

    if ffmpeg_key in env_map and env_map[ffmpeg_key].strip():
        config_data["render"]["ffmpeg_path"] = env_map[ffmpeg_key].strip()

    if workers_key in env_map and env_map[workers_key].strip():
        try:
            config_data["render"]["workers"] = int(env_map[workers_key].strip())
        except ValueError as exc:
            raise ConfigLoadError(
                f"Environment variable {workers_key} must be an integer."
            ) from exc

    if debug_key in env_map and env_map[debug_key].strip():
        debug_raw = env_map[debug_key].strip().lower()
        is_debug = debug_raw in {"1", "true", "yes", "on"}
        config_data["advanced"]["debug_mode"] = is_debug
        if is_debug:
            config_data["logging"]["level"] = "DEBUG"


def build_settings(config_path: Path, project_root: Path, data: Mapping[str, Any]) -> Settings:
    """Convert merged configuration mapping into strongly typed settings."""
    return Settings(
        config_path=config_path,
        project_root=project_root,
        project=ProjectSettings(**data["project"]),
        paths=PathSettings(**data["paths"]),
        render=RenderSettings(**data["render"]),
        shorts=ProfileSettings(
            enabled=bool(data["shorts"]["enabled"]),
            resolution=Resolution(**data["shorts"]["resolution"]),
            fps=int(data["shorts"]["fps"]),
            duration=DurationSettings(**data["shorts"]["duration"]),
        ),
        long=ProfileSettings(
            enabled=bool(data["long"]["enabled"]),
            resolution=Resolution(**data["long"]["resolution"]),
            fps=int(data["long"]["fps"]),
            duration=DurationSettings(**data["long"]["duration"]),
        ),
        images=ImageSettings(**data["images"]),
        videos=VideoSettings(
            clip_duration=ClipDurationSettings(**data["videos"]["clip_duration"]),
            shuffle=bool(data["videos"]["shuffle"]),
            mute_original_audio=bool(data["videos"]["mute_original_audio"]),
        ),
        transitions=TransitionSettings(**data["transitions"]),
        color_grading=ColorGradingSettings(**data["color_grading"]),
        audio=AudioEngineSettings(**data["audio"]),
        text_overlay=TextOverlaySettings(**data["text_overlay"]),
        overlays=OverlaySettings(
            header=OverlayItemSettings(**data["overlays"]["header"]),
            footer=OverlayItemSettings(**data["overlays"]["footer"]),
            socials=OverlayItemSettings(**data["overlays"]["socials"]),
            website=OverlayItemSettings(**data["overlays"]["website"]),
        ),
        thumbnails=ThumbnailSettings(**data["thumbnails"]),
        media_analyzer=MediaAnalyzerSettings(
            minimum_resolution=Resolution(**data["media_analyzer"]["minimum_resolution"]),
            ignore_corrupted_files=bool(data["media_analyzer"]["ignore_corrupted_files"]),
            ignore_hidden_files=bool(data["media_analyzer"]["ignore_hidden_files"]),
            supported_extensions=list(data["media_analyzer"]["supported_extensions"]),
        ),
        organizer=OrganizerSettings(**data["organizer"]),
        review=ReviewSettings(**data["review"]),
        logging=LoggingSettings(**data["logging"]),
        reports=ReportSettings(**data["reports"]),
        advanced=AdvancedSettings(**data["advanced"]),
        environment=EnvironmentSettings(**data["environment"]),
    )
