"""Persistence utilities for resumable review progress."""

from __future__ import annotations

import json
from pathlib import Path

from src.review.models import ReviewProgress


def load_progress(progress_path: Path) -> ReviewProgress:
    """Load review progress from JSON, returning default progress when missing."""
    if not progress_path.exists() or not progress_path.is_file():
        return ReviewProgress()

    try:
        payload = json.loads(progress_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ReviewProgress()

    if not isinstance(payload, dict):
        return ReviewProgress()

    return ReviewProgress(
        current_index=int(payload.get("current_index", 0)),
        accepted=[str(item) for item in payload.get("accepted", []) if isinstance(item, str)],
        rejected=[str(item) for item in payload.get("rejected", []) if isinstance(item, str)],
        skipped=[str(item) for item in payload.get("skipped", []) if isinstance(item, str)],
    )


def save_progress(progress_path: Path, progress: ReviewProgress) -> None:
    """Persist review progress state."""
    payload = {
        "current_index": progress.current_index,
        "accepted": progress.accepted,
        "rejected": progress.rejected,
        "skipped": progress.skipped,
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
