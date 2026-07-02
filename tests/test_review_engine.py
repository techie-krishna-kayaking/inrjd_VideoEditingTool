"""Unit tests for CLI-based review engine and helpers."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from rich.console import Console

from src.review.discovery import build_review_queue
from src.review.engine import ReviewEngine
from src.review.keys import map_key_to_action
from src.review.models import ReviewFilterOptions, ReviewRunConfig


def _write_image(path: Path, width: int, height: int) -> None:
    """Create a valid image file for review tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), color=(128, 128, 128))
    image.save(path)


def test_key_mapping_shortcuts() -> None:
    """Shortcuts should map to normalized review actions."""
    assert map_key_to_action("k") == "keep"
    assert map_key_to_action("r") == "reject"
    assert map_key_to_action("s") == "skip"
    assert map_key_to_action("b") == "back"
    assert map_key_to_action("n") == "next"
    assert map_key_to_action("q") == "quit"
    assert map_key_to_action("left") == "back"
    assert map_key_to_action("right") == "next"
    assert map_key_to_action("enter") == "keep"
    assert map_key_to_action("esc") == "quit"


def test_build_queue_duplicate_filter(tmp_path: Path) -> None:
    """Duplicate filter should keep only duplicate media candidates."""
    event_name = "2026-Feb-Gaura Purnima"
    bucket = tmp_path / "input" / event_name / "shortform_pictures"
    bucket.mkdir(parents=True, exist_ok=True)

    first = bucket / "a.jpg"
    second = bucket / "b.jpg"
    third = bucket / "c.jpg"
    first.write_bytes(b"same-content")
    second.write_bytes(b"same-content")
    third.write_bytes(b"different-content")

    queue = build_review_queue(
        input_root=tmp_path / "input",
        event_name=event_name,
        bucket_filter="shortform_pictures",
        filters=ReviewFilterOptions(duplicates=True),
        low_quality_threshold=45,
    )

    assert len(queue) == 2
    assert {item.path.name for item in queue} == {"a.jpg", "b.jpg"}


def test_review_engine_rejects_and_reports(tmp_path: Path) -> None:
    """Review engine should move rejected file and generate review report."""
    event_name = "2026-Apr-Ram Navami"
    input_root = tmp_path / "input"
    bucket = input_root / event_name / "shortform_pictures"
    _write_image(bucket / "keep.jpg", width=1080, height=1920)
    _write_image(bucket / "reject.jpg", width=1080, height=1920)

    actions = iter(["k", "r"])

    def _read_key() -> str:
        return next(actions)

    config = ReviewRunConfig(
        input_root=input_root,
        reviewer="tester",
        open_with_default_viewer=False,
        low_quality_threshold=45,
        estimated_seconds_per_item=1.0,
        progress_file_name="review_progress.json",
        report_file_name="review_report.json",
    )
    engine = ReviewEngine(config=config, console=Console(record=True), key_reader=_read_key)

    results = engine.run(
        event_name=event_name,
        all_events=False,
        media_type_bucket="shortform_pictures",
        resume=False,
        filters=ReviewFilterOptions(),
    )

    assert len(results) == 1
    result = results[0]
    assert result.accepted == 1
    assert result.rejected == 1

    rejected_dir = input_root / event_name / "rejected"
    assert (rejected_dir / "reject.jpg").exists()

    report_path = input_root / event_name / "reports" / "review_report.json"
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_data["reviewer"] == "tester"
    assert len(report_data["accepted"]) == 1
    assert len(report_data["rejected"]) == 1


def test_review_engine_resume_continues_from_saved_progress(tmp_path: Path) -> None:
    """Resume should continue from saved index and preserve previous decisions."""
    event_name = "2026-Jan-New Year Celebrations"
    input_root = tmp_path / "input"
    bucket = input_root / event_name / "longform_pictures"
    _write_image(bucket / "one.jpg", width=1920, height=1080)
    _write_image(bucket / "two.jpg", width=1920, height=1080)

    first_actions = iter(["s", "q"])

    def _first_key() -> str:
        return next(first_actions)

    config = ReviewRunConfig(
        input_root=input_root,
        reviewer="resume-user",
        open_with_default_viewer=False,
        low_quality_threshold=45,
        estimated_seconds_per_item=1.0,
        progress_file_name="review_progress.json",
        report_file_name="review_report.json",
    )

    first_engine = ReviewEngine(config=config, console=Console(record=True), key_reader=_first_key)
    first_engine.run(
        event_name=event_name,
        all_events=False,
        media_type_bucket="longform_pictures",
        resume=False,
        filters=ReviewFilterOptions(),
    )

    second_actions = iter(["k"])

    def _second_key() -> str:
        return next(second_actions)

    second_engine = ReviewEngine(config=config, console=Console(record=True), key_reader=_second_key)
    results = second_engine.run(
        event_name=event_name,
        all_events=False,
        media_type_bucket="longform_pictures",
        resume=True,
        filters=ReviewFilterOptions(),
    )

    assert len(results) == 1
    result = results[0]
    assert result.accepted == 1
    assert result.skipped == 1
