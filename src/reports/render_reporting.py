"""Render reporting, media usage tracking, and history persistence utilities."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RenderArtifacts:
    """Paths for generated report artifacts."""

    json_path: Path
    csv_path: Path
    txt_path: Path


def write_report_artifacts(report_path: Path, payload: dict[str, Any]) -> RenderArtifacts:
    """Write JSON/CSV/TXT report variants for one render payload."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    json_path = report_path
    csv_path = report_path.with_suffix(".csv")
    txt_path = report_path.with_suffix(".txt")

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rows = _flatten_output_rows(payload)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "event",
                "workflow",
                "output_file",
                "timeline_duration",
                "render_time",
                "output_size",
                "clips",
                "transitions",
                "music_tracks",
                "gpu_used",
                "created_at",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    txt_path.write_text(_format_text_summary(payload, rows), encoding="utf-8")

    return RenderArtifacts(json_path=json_path, csv_path=csv_path, txt_path=txt_path)


def update_media_usage(
    media_usage_path: Path,
    media_records: list[dict[str, Any]],
    workflow: str,
) -> None:
    """Update media usage database with render counts and last-used timestamps."""
    state = _load_json(media_usage_path, {"media": {}})
    media_map = state.setdefault("media", {})
    if not isinstance(media_map, dict):
        media_map = {}
        state["media"] = media_map

    now = datetime.now(timezone.utc).isoformat()

    for record in media_records:
        path_value = str(record.get("path", "")).strip()
        if not path_value:
            continue
        media_type = str(record.get("type", "unknown")).strip().lower() or "unknown"
        key = f"{media_type}:{path_value}"
        existing = media_map.get(key)

        if not isinstance(existing, dict):
            existing = {
                "path": path_value,
                "type": media_type,
                "render_count": 0,
                "last_used_date": None,
                "video_name": Path(path_value).name,
                "workflow": workflow,
            }

        existing["render_count"] = int(existing.get("render_count", 0)) + 1
        existing["last_used_date"] = now
        existing["workflow"] = workflow
        existing["video_name"] = Path(path_value).name
        media_map[key] = existing

    state["updated_at"] = now
    _write_json(media_usage_path, state)


def append_render_history(render_history_path: Path, history_record: dict[str, Any]) -> None:
    """Append one render record to render_history.json."""
    state = _load_json(render_history_path, {"history": []})
    entries = state.setdefault("history", [])
    if not isinstance(entries, list):
        entries = []
        state["history"] = entries

    entries.append(history_record)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(render_history_path, state)


def _flatten_output_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten output list for CSV export."""
    event = str(payload.get("event_name", ""))
    workflow = str(payload.get("mode", ""))
    gpu_used = str(payload.get("gpu_used", "cpu"))
    created_at = str(payload.get("generated_at", ""))

    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "event": event,
                "workflow": workflow,
                "output_file": str(item.get("output_file", "")),
                "timeline_duration": item.get("timeline_duration", 0),
                "render_time": item.get("render_time", 0),
                "output_size": item.get("output_size", 0),
                "clips": len(item.get("clip_positions", [])) if isinstance(item.get("clip_positions"), list) else 0,
                "transitions": len(item.get("transitions", [])) if isinstance(item.get("transitions"), list) else 0,
                "music_tracks": len(item.get("music", [])) if isinstance(item.get("music"), list) else 0,
                "gpu_used": gpu_used,
                "created_at": created_at,
            }
        )

    return rows


def _format_text_summary(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """Format plain-text summary report with render/media statistics."""
    event = str(payload.get("event_name", ""))
    mode = str(payload.get("mode", ""))
    total_render = payload.get("render_time_total", 0)
    videos_used = payload.get("videos_used", [])
    output_count = len(rows)
    total_output_size = sum(int(row.get("output_size", 0) or 0) for row in rows)

    lines = [
        "Render Summary",
        "============",
        f"Event: {event}",
        f"Workflow: {mode}",
        f"Outputs: {output_count}",
        f"Videos analyzed: {len(videos_used) if isinstance(videos_used, list) else 0}",
        f"Render time total: {total_render}",
        f"Output size total: {total_output_size}",
        f"GPU used: {payload.get('gpu_used', 'cpu')}",
        "",
        "Output Details",
        "--------------",
    ]

    for row in rows:
        lines.append(
            f"- {row['output_file']} | duration={row['timeline_duration']} | clips={row['clips']} "
            f"| transitions={row['transitions']} | music_tracks={row['music_tracks']}"
        )

    return "\n".join(lines) + "\n"


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    """Load JSON mapping with fallback for missing/invalid files."""
    if not path.exists():
        return fallback.copy()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return fallback.copy()

    if not isinstance(data, dict):
        return fallback.copy()
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON file ensuring parent path exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
