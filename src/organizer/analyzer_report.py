"""Analyzer report loading for organizer workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.organizer.exceptions import AnalyzerReportFormatError, AnalyzerReportMissingError
from src.organizer.models import AnalyzerMediaEntry


def load_analyzer_entries(report_path: Path) -> list[AnalyzerMediaEntry]:
    """Load analyzer JSON report and return normalized media entries."""
    if not report_path.exists() or not report_path.is_file():
        raise AnalyzerReportMissingError(
            "Please run\npython main.py analyze\nbefore organizing."
        )

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnalyzerReportFormatError(f"Invalid analyzer report JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise AnalyzerReportFormatError("Analyzer report root must be a JSON object.")

    entries: list[AnalyzerMediaEntry] = []
    if isinstance(payload.get("events"), list):
        entries.extend(_parse_grouped_events(payload["events"]))
    if isinstance(payload.get("media"), list):
        entries.extend(_parse_flat_media(payload["media"]))

    if not entries:
        raise AnalyzerReportFormatError("Analyzer report does not contain usable media entries.")

    return entries


def _parse_grouped_events(events: list[Any]) -> list[AnalyzerMediaEntry]:
    """Parse grouped schema: {events: [{event_name, files:[...]}]}"""
    entries: list[AnalyzerMediaEntry] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event_name", "")).strip()
        files = event.get("files")
        if not event_name or not isinstance(files, list):
            continue
        for item in files:
            entry = _parse_entry(item=item, event_name=event_name)
            if entry is not None:
                entries.append(entry)
    return entries


def _parse_flat_media(media_items: list[Any]) -> list[AnalyzerMediaEntry]:
    """Parse flat schema: {media: [{event_name, ...}, ...]}"""
    entries: list[AnalyzerMediaEntry] = []
    for item in media_items:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event_name", "")).strip()
        if not event_name:
            continue
        entry = _parse_entry(item=item, event_name=event_name)
        if entry is not None:
            entries.append(entry)
    return entries


def _parse_entry(item: dict[str, Any], event_name: str) -> AnalyzerMediaEntry | None:
    """Parse one analyzer media record into a typed entry."""
    path_raw = item.get("source_path") or item.get("path")
    if not isinstance(path_raw, str) or not path_raw.strip():
        return None

    media_type_raw = str(item.get("media_type", "")).strip().lower()
    if media_type_raw not in {"image", "video"}:
        media_type_raw = _infer_media_type_from_extension(Path(path_raw).suffix.lower())
        if media_type_raw is None:
            return None

    width = _to_int(item.get("width"))
    height = _to_int(item.get("height"))
    size_bytes = _to_int(item.get("size_bytes") or item.get("size"))
    modified_ts = _to_float(item.get("modified_ts") or item.get("mtime"))

    checksum_raw = item.get("checksum")
    checksum = str(checksum_raw).strip() if isinstance(checksum_raw, str) and checksum_raw.strip() else None

    return AnalyzerMediaEntry(
        event_name=event_name,
        source_path=Path(path_raw),
        media_type=media_type_raw,
        width=width,
        height=height,
        size_bytes=size_bytes,
        checksum=checksum,
        modified_ts=modified_ts,
    )


def _infer_media_type_from_extension(extension: str) -> str | None:
    """Infer media type from extension when analyzer omits media_type."""
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff"}
    video_extensions = {".mp4", ".mov", ".avi", ".mts", ".mkv", ".m4v", ".webm"}
    if extension in image_extensions:
        return "image"
    if extension in video_extensions:
        return "video"
    return None


def _to_int(value: Any) -> int | None:
    """Convert unknown numeric input into int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    """Convert unknown numeric input into float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
