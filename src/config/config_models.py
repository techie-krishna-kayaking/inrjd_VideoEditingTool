"""Strongly typed configuration models for the media engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ProjectSettings:
    """General project metadata."""

    name: str
    version: str
    author: str
    organization: str


@dataclass(slots=True)
class PathSettings:
    """Filesystem path settings used by all runtime modules."""

    raw_data: str
    input: str
    output: str
    assets: str
    music: str
    reports: str
    logs: str
    temp: str


@dataclass(slots=True)
class Resolution:
    """Resolution model for video and image outputs."""

    width: int
    height: int


@dataclass(slots=True)
class DurationSettings:
    """Duration bounds in seconds."""

    minimum: int
    default: int
    maximum: int


@dataclass(slots=True)
class RenderSettings:
    """Render orchestration and runtime controls."""

    workers: int
    gpu_auto_detect: bool
    overwrite_existing: bool
    resume_failed: bool
    create_reports: bool
    create_logs: bool
    create_thumbnail: bool
    preferred_encoder: str
    ffmpeg_path: str


@dataclass(slots=True)
class ProfileSettings:
    """Output profile settings for short and long formats."""

    enabled: bool
    resolution: Resolution
    fps: int
    duration: DurationSettings


@dataclass(slots=True)
class ImageSettings:
    """Image sequencing and animation controls."""

    random_order: bool
    image_duration: float
    reuse_images: bool
    avoid_recent_repeat: int
    enable_ken_burns: bool
    animation_random: bool


@dataclass(slots=True)
class ClipDurationSettings:
    """Video clip duration ranges."""

    minimum: int
    maximum: int


@dataclass(slots=True)
class VideoSettings:
    """Video source handling controls."""

    clip_duration: ClipDurationSettings
    shuffle: bool
    mute_original_audio: bool


@dataclass(slots=True)
class TransitionSettings:
    """Transition engine controls."""

    hard_cut: bool
    cross_dissolve: bool
    film_burn: bool
    morph_cut: bool
    match_cut: bool
    random_selection: bool
    duration: float


@dataclass(slots=True)
class ColorGradingSettings:
    """Conservative color grading controls."""

    brightness: float
    contrast: float
    saturation: float
    sharpen: float
    gamma: float


@dataclass(slots=True)
class AudioEngineSettings:
    """Audio automation controls."""

    random_music: bool
    random_start_position: bool
    fade_in: float
    fade_out: float
    normalize_loudness: bool
    music_volume: float
    crossfade: float


@dataclass(slots=True)
class TextOverlaySettings:
    """Text overlay controls for intro/title sequences."""

    opening_title: str
    animation: str
    tilt: float
    glass_effect: bool
    duration: float
    font: str
    shadow: bool
    outline: bool


@dataclass(slots=True)
class OverlayItemSettings:
    """Overlay asset placement controls."""

    enabled: bool
    file: str
    opacity: float
    margin_top: int
    margin_bottom: int
    margin_left: int
    margin_right: int


@dataclass(slots=True)
class OverlaySettings:
    """Overlay asset configuration for header/footer/socials/website."""

    header: OverlayItemSettings
    footer: OverlayItemSettings
    socials: OverlayItemSettings
    website: OverlayItemSettings


@dataclass(slots=True)
class ThumbnailSettings:
    """Thumbnail generation controls."""

    generate: bool
    width: int
    height: int
    jpeg_quality: int


@dataclass(slots=True)
class MediaAnalyzerSettings:
    """Media analyzer validation and extension controls."""

    minimum_resolution: Resolution
    ignore_corrupted_files: bool
    ignore_hidden_files: bool
    supported_extensions: list[str]


@dataclass(slots=True)
class OrganizerSettings:
    """Folder creation controls for organized inputs."""

    shortform_pictures: bool
    shortform_videos: bool
    longform_pictures: bool
    longform_videos: bool
    rejected: bool
    copy_strategy: str = "copy"
    analyzer_report: str = "output/reports/analyzer_report.json"


@dataclass(slots=True)
class ReviewSettings:
    """Interactive review engine settings."""

    open_with_default_viewer: bool
    reviewer: str
    low_quality_threshold: int
    estimated_seconds_per_item: float
    progress_file: str
    report_file: str


@dataclass(slots=True)
class LoggingSettings:
    """Runtime logging controls."""

    console: bool
    file: bool
    level: str
    rotation: str
    retention: str


@dataclass(slots=True)
class ReportSettings:
    """Report generation controls."""

    json: bool
    csv: bool
    summary: bool
    statistics: bool


@dataclass(slots=True)
class AdvancedSettings:
    """Advanced runtime controls."""

    experimental_features: bool
    dry_run: bool
    debug_mode: bool
    developer_mode: bool


@dataclass(slots=True)
class EnvironmentSettings:
    """Environment override key definitions."""

    dotenv_enabled: bool
    output_folder_key: str
    ffmpeg_path_key: str
    workers_key: str
    debug_key: str


@dataclass(slots=True)
class Settings:
    """Root strongly typed settings object."""

    config_path: Path
    project_root: Path
    project: ProjectSettings
    paths: PathSettings
    render: RenderSettings
    shorts: ProfileSettings
    long: ProfileSettings
    images: ImageSettings
    videos: VideoSettings
    transitions: TransitionSettings
    color_grading: ColorGradingSettings
    audio: AudioEngineSettings
    text_overlay: TextOverlaySettings
    overlays: OverlaySettings
    thumbnails: ThumbnailSettings
    media_analyzer: MediaAnalyzerSettings
    organizer: OrganizerSettings
    review: ReviewSettings
    logging: LoggingSettings
    reports: ReportSettings
    advanced: AdvancedSettings
    environment: EnvironmentSettings
