"""Typed models for review engine configuration and runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ReviewAction = Literal["keep", "reject", "skip", "back", "next", "quit"]
Orientation = Literal["portrait", "landscape", "unknown"]
MediaType = Literal["image", "video", "unknown"]


@dataclass(slots=True)
class ReviewFilterOptions:
    """CLI filter options for narrowing review candidates."""

    portrait_images: bool = False
    landscape_images: bool = False
    videos: bool = False
    low_quality: bool = False
    duplicates: bool = False


@dataclass(slots=True)
class ReviewRunConfig:
    """Runtime configuration for review sessions."""

    input_root: Path
    reviewer: str
    open_with_default_viewer: bool
    low_quality_threshold: int
    estimated_seconds_per_item: float
    progress_file_name: str
    report_file_name: str


@dataclass(slots=True)
class ReviewMediaItem:
    """Single media candidate in review queue."""

    event_name: str
    bucket: str
    path: Path
    media_type: MediaType
    orientation: Orientation
    width: int | None
    height: int | None
    size_bytes: int
    quality_score: int | None
    duplicate_key: str | None


@dataclass(slots=True)
class ReviewProgress:
    """Persisted progress for resumable review sessions."""

    current_index: int = 0
    accepted: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EventReviewResult:
    """Per-event summary produced by the review engine."""

    event_name: str
    total_items: int
    reviewed_items: int
    accepted: int
    rejected: int
    skipped: int
    duration_seconds: float
    report_path: Path
