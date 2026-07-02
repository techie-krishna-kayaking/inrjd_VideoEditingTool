"""Unit tests for analyzer-driven media organizer workflows."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.organizer.exceptions import AnalyzerReportMissingError
from src.organizer.service import MediaOrganizer


def _write_config(config_path: Path, analyzer_report: str) -> None:
    """Write minimal organizer config used by tests."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "organizer": {
            "copy_strategy": "copy",
            "analyzer_report": analyzer_report,
        }
    }
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_report(report_path: Path, report_payload: dict[str, object]) -> None:
    """Write analyzer report payload for organizer tests."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")


def test_organize_requires_analyzer_report(tmp_path: Path) -> None:
    """Organizer should fail with actionable message when analyzer report is missing."""
    project_root = tmp_path / "project"
    config_path = project_root / "config.yaml"
    _write_config(config_path=config_path, analyzer_report="output/reports/analyzer_report.json")

    organizer = MediaOrganizer(
        project_root=project_root,
        config_path=config_path,
        input_root=project_root / "input",
        reports_root=project_root / "output" / "reports",
    )

    try:
        organizer.organize(event_name=None, all_events=True, override_mode=None)
    except AnalyzerReportMissingError as exc:
        assert "python main.py analyze" in str(exc)
    else:
        raise AssertionError("Expected AnalyzerReportMissingError")


def test_organize_classifies_and_writes_reports(tmp_path: Path) -> None:
    """Organizer should classify media and generate event reports."""
    project_root = tmp_path / "project"
    output_reports = project_root / "output" / "reports"
    config_path = project_root / "config.yaml"
    _write_config(config_path=config_path, analyzer_report="output/reports/analyzer_report.json")

    event_name = "2026-Feb-Gaura Purnima"
    source_dir = project_root / "raw_data" / event_name
    source_dir.mkdir(parents=True, exist_ok=True)

    portrait_image = source_dir / "portrait.jpg"
    landscape_image = source_dir / "landscape.png"
    portrait_video = source_dir / "portrait.mp4"
    landscape_video = source_dir / "landscape.mov"
    unsupported = source_dir / "note.txt"

    portrait_image.write_bytes(b"img-a")
    landscape_image.write_bytes(b"img-b")
    portrait_video.write_bytes(b"vid-a")
    landscape_video.write_bytes(b"vid-b")
    unsupported.write_bytes(b"skip")

    _write_report(
        report_path=output_reports / "analyzer_report.json",
        report_payload={
            "events": [
                {
                    "event_name": event_name,
                    "files": [
                        {
                            "source_path": str(portrait_image),
                            "media_type": "image",
                            "width": 1080,
                            "height": 1920,
                            "size_bytes": 5,
                            "checksum": "img1",
                        },
                        {
                            "source_path": str(landscape_image),
                            "media_type": "image",
                            "width": 1920,
                            "height": 1080,
                            "size_bytes": 5,
                            "checksum": "img2",
                        },
                        {
                            "source_path": str(portrait_video),
                            "media_type": "video",
                            "width": 1080,
                            "height": 1920,
                            "size_bytes": 5,
                            "checksum": "vid1",
                        },
                        {
                            "source_path": str(landscape_video),
                            "media_type": "video",
                            "width": 1920,
                            "height": 1080,
                            "size_bytes": 5,
                            "checksum": "vid2",
                        },
                        {
                            "source_path": str(unsupported),
                            "media_type": "image",
                            "width": 500,
                            "height": 500,
                            "size_bytes": 4,
                            "checksum": "bad1",
                        },
                    ],
                }
            ]
        },
    )

    organizer = MediaOrganizer(
        project_root=project_root,
        config_path=config_path,
        input_root=project_root / "input",
        reports_root=output_reports,
    )
    result = organizer.organize(event_name=None, all_events=True, override_mode="copy")

    assert len(result.events) == 1
    stats = result.events[0].stats
    assert stats.portrait_images == 1
    assert stats.landscape_images == 1
    assert stats.portrait_videos == 1
    assert stats.landscape_videos == 1
    assert stats.rejected == 1
    assert stats.copied == 5

    event_root = project_root / "input" / event_name
    assert (event_root / "shortform_pictures" / "portrait.jpg").exists()
    assert (event_root / "longform_pictures" / "landscape.png").exists()
    assert (event_root / "shortform_videos" / "portrait.mp4").exists()
    assert (event_root / "longform_videos" / "landscape.mov").exists()
    assert (event_root / "rejected" / "note.txt").exists()

    reports_dir = event_root / "reports"
    assert (reports_dir / "organization_report.json").exists()
    assert (reports_dir / "organization_report.csv").exists()
    assert (reports_dir / "organization_summary.txt").exists()


def test_organize_link_mode_creates_symlink(tmp_path: Path) -> None:
    """Organizer should support symbolic-link mode."""
    project_root = tmp_path / "project"
    output_reports = project_root / "output" / "reports"
    config_path = project_root / "config.yaml"
    _write_config(config_path=config_path, analyzer_report="output/reports/analyzer_report.json")

    event_name = "2026-Apr-Ram Navami"
    source_dir = project_root / "raw_data" / event_name
    source_dir.mkdir(parents=True, exist_ok=True)
    image_file = source_dir / "bhajan.webp"
    image_file.write_bytes(b"image")

    _write_report(
        report_path=output_reports / "analyzer_report.json",
        report_payload={
            "media": [
                {
                    "event_name": event_name,
                    "source_path": str(image_file),
                    "media_type": "image",
                    "width": 1080,
                    "height": 1920,
                    "size_bytes": 5,
                    "checksum": "link1",
                }
            ]
        },
    )

    organizer = MediaOrganizer(
        project_root=project_root,
        config_path=config_path,
        input_root=project_root / "input",
        reports_root=output_reports,
    )
    result = organizer.organize(event_name=None, all_events=True, override_mode="link")

    stats = result.events[0].stats
    assert stats.linked == 1
    linked_path = project_root / "input" / event_name / "shortform_pictures" / "bhajan.webp"
    assert linked_path.is_symlink()


def test_organize_resume_duplicate_rename_and_modified_detection(tmp_path: Path) -> None:
    """Organizer should skip duplicates and handle renamed/modified sources on resume."""
    project_root = tmp_path / "project"
    output_reports = project_root / "output" / "reports"
    config_path = project_root / "config.yaml"
    _write_config(config_path=config_path, analyzer_report="output/reports/analyzer_report.json")

    event_name = "2026-Jan-New Year Celebrations"
    source_dir = project_root / "raw_data" / event_name
    source_dir.mkdir(parents=True, exist_ok=True)

    file_a = source_dir / "a.jpg"
    file_b = source_dir / "renamed_b.jpg"
    file_a.write_bytes(b"abc")
    file_b.write_bytes(b"abc")

    report_path = output_reports / "analyzer_report.json"
    _write_report(
        report_path=report_path,
        report_payload={
            "events": [
                {
                    "event_name": event_name,
                    "files": [
                        {
                            "source_path": str(file_a),
                            "media_type": "image",
                            "width": 1080,
                            "height": 1920,
                            "size_bytes": 3,
                            "checksum": "same-sig",
                        },
                        {
                            "source_path": str(file_b),
                            "media_type": "image",
                            "width": 1080,
                            "height": 1920,
                            "size_bytes": 3,
                            "checksum": "same-sig",
                        },
                    ],
                }
            ]
        },
    )

    organizer = MediaOrganizer(
        project_root=project_root,
        config_path=config_path,
        input_root=project_root / "input",
        reports_root=output_reports,
    )

    first_result = organizer.organize(event_name=event_name, all_events=False, override_mode="copy")
    first_stats = first_result.events[0].stats
    assert first_stats.copied == 1
    assert first_stats.skipped == 1

    file_a.write_bytes(b"abcdef")
    _write_report(
        report_path=report_path,
        report_payload={
            "events": [
                {
                    "event_name": event_name,
                    "files": [
                        {
                            "source_path": str(file_a),
                            "media_type": "image",
                            "width": 1080,
                            "height": 1920,
                            "size_bytes": 6,
                            "checksum": "new-sig",
                        }
                    ],
                }
            ]
        },
    )

    second_result = organizer.organize(event_name=event_name, all_events=False, override_mode="copy")
    second_stats = second_result.events[0].stats
    assert second_stats.copied == 1
    assert len(second_result.events[0].warnings) >= 1

    copied_dir = project_root / "input" / event_name / "shortform_pictures"
    copied_files = list(copied_dir.glob("*.jpg"))
    assert len(copied_files) == 2
