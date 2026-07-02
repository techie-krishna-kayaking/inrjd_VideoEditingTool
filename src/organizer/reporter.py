"""Organization report writers (JSON, CSV, and summary text)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.organizer.models import EventOrganizationResult, OrganizerRunResult


def write_event_reports(reports_dir: Path, event_result: EventOrganizationResult, mode: str) -> None:
    """Write event-level organization report files."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    _write_json(path=reports_dir / "organization_report.json", event_result=event_result, mode=mode)
    _write_csv(path=reports_dir / "organization_report.csv", event_result=event_result, mode=mode)
    _write_summary(path=reports_dir / "organization_summary.txt", event_result=event_result, mode=mode)


def write_run_summary(output_reports_dir: Path, run_result: OrganizerRunResult) -> Path:
    """Write a run-level summary report under output/reports."""
    output_reports_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_reports_dir / "organizer_run_summary.txt"

    lines: list[str] = []
    lines.append("Organizer Run Summary")
    lines.append(f"Mode: {run_result.mode}")
    lines.append(f"Duration Seconds: {run_result.duration_seconds:.2f}")
    lines.append("")

    for event in run_result.events:
        stats = event.stats
        lines.append(f"Event: {stats.event_name}")
        lines.append(f"Portrait Images: {stats.portrait_images}")
        lines.append(f"Landscape Images: {stats.landscape_images}")
        lines.append(f"Portrait Videos: {stats.portrait_videos}")
        lines.append(f"Landscape Videos: {stats.landscape_videos}")
        lines.append(f"Rejected: {stats.rejected}")
        lines.append(f"Total Copied: {stats.copied}")
        lines.append(f"Total Linked: {stats.linked}")
        lines.append(f"Total Size: {stats.total_size_bytes}")
        lines.append("")

    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return summary_path


def _write_json(path: Path, event_result: EventOrganizationResult, mode: str) -> None:
    """Persist event-level JSON report."""
    stats = event_result.stats
    payload = {
        "event_name": stats.event_name,
        "mode": mode,
        "portrait_images": stats.portrait_images,
        "landscape_images": stats.landscape_images,
        "portrait_videos": stats.portrait_videos,
        "landscape_videos": stats.landscape_videos,
        "rejected": stats.rejected,
        "total_copied": stats.copied,
        "total_linked": stats.linked,
        "total_size": stats.total_size_bytes,
        "skipped": stats.skipped,
        "errors": event_result.errors,
        "warnings": event_result.warnings,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, event_result: EventOrganizationResult, mode: str) -> None:
    """Persist event-level CSV report."""
    stats = event_result.stats
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "event_name",
                "mode",
                "portrait_images",
                "landscape_images",
                "portrait_videos",
                "landscape_videos",
                "rejected",
                "total_copied",
                "total_linked",
                "total_size",
                "skipped",
                "errors_count",
                "warnings_count",
            ]
        )
        writer.writerow(
            [
                stats.event_name,
                mode,
                stats.portrait_images,
                stats.landscape_images,
                stats.portrait_videos,
                stats.landscape_videos,
                stats.rejected,
                stats.copied,
                stats.linked,
                stats.total_size_bytes,
                stats.skipped,
                len(event_result.errors),
                len(event_result.warnings),
            ]
        )


def _write_summary(path: Path, event_result: EventOrganizationResult, mode: str) -> None:
    """Persist event-level human-readable summary report."""
    stats = event_result.stats
    lines = [
        f"Event Name: {stats.event_name}",
        f"Mode: {mode}",
        f"Portrait Images: {stats.portrait_images}",
        f"Landscape Images: {stats.landscape_images}",
        f"Portrait Videos: {stats.portrait_videos}",
        f"Landscape Videos: {stats.landscape_videos}",
        f"Rejected: {stats.rejected}",
        f"Total Copied: {stats.copied}",
        f"Total Linked: {stats.linked}",
        f"Total Size: {stats.total_size_bytes}",
        f"Skipped: {stats.skipped}",
        f"Warnings: {len(event_result.warnings)}",
        f"Errors: {len(event_result.errors)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
