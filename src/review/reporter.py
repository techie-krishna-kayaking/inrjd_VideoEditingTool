"""Report writer for review engine outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.review.models import ReviewProgress


def write_review_report(
    report_path: Path,
    event_name: str,
    reviewer: str,
    duration_seconds: float,
    progress: ReviewProgress,
) -> Path:
    """Write event review report as JSON."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_name": event_name,
        "date": datetime.now(tz=timezone.utc).isoformat(),
        "reviewer": reviewer,
        "duration_seconds": round(duration_seconds, 3),
        "accepted": progress.accepted,
        "rejected": progress.rejected,
        "skipped": progress.skipped,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path
