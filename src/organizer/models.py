"""Typed models used by organizer workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AnalyzerMediaEntry:
    """Single media record produced by analyzer output."""

    event_name: str
    source_path: Path
    media_type: str
    width: int | None
    height: int | None
    size_bytes: int | None
    checksum: str | None
    modified_ts: float | None


@dataclass(slots=True)
class EventOrganizationStats:
    """Per-event organization counters used in logs, CLI, and reports."""

    event_name: str
    portrait_images: int = 0
    landscape_images: int = 0
    portrait_videos: int = 0
    landscape_videos: int = 0
    rejected: int = 0
    copied: int = 0
    moved: int = 0
    linked: int = 0
    skipped: int = 0
    errors: int = 0
    total_size_bytes: int = 0


@dataclass(slots=True)
class EventOrganizationResult:
    """Per-event organization outcome including file-level warnings/errors."""

    stats: EventOrganizationStats
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OrganizerRunResult:
    """Aggregate result for one organizer run."""

    mode: str
    duration_seconds: float
    events: list[EventOrganizationResult] = field(default_factory=list)
