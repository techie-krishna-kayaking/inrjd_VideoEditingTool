"""State persistence utilities for resumable organization runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.organizer.models import AnalyzerMediaEntry


@dataclass(slots=True)
class OrganizerState:
    """Per-event state persisted for idempotency and resume support."""

    by_signature: dict[str, dict[str, Any]]
    by_source: dict[str, dict[str, Any]]


def load_state(state_path: Path) -> OrganizerState:
    """Load organizer state from JSON, returning empty state when missing."""
    if not state_path.exists() or not state_path.is_file():
        return OrganizerState(by_signature={}, by_source={})

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return OrganizerState(by_signature={}, by_source={})

    if not isinstance(payload, dict):
        return OrganizerState(by_signature={}, by_source={})

    by_signature = payload.get("by_signature")
    by_source = payload.get("by_source")

    if not isinstance(by_signature, dict):
        by_signature = {}
    if not isinstance(by_source, dict):
        by_source = {}

    return OrganizerState(by_signature=by_signature, by_source=by_source)


def save_state(state_path: Path, state: OrganizerState) -> None:
    """Persist organizer state atomically."""
    payload = {
        "by_signature": state.by_signature,
        "by_source": state.by_source,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def source_signature(entry: AnalyzerMediaEntry) -> str:
    """Build stable source signature used for duplicate/rename detection."""
    if entry.checksum:
        return f"checksum:{entry.checksum}"

    size_part = entry.size_bytes if entry.size_bytes is not None else "unknown"
    mtime_part = entry.modified_ts if entry.modified_ts is not None else "unknown"
    return f"stat:{size_part}:{mtime_part}:{entry.source_path.suffix.lower()}"


def current_source_fingerprint(path: Path) -> str:
    """Build source fingerprint from filesystem metadata for modified detection."""
    stat = path.stat()
    return f"{int(stat.st_mtime)}:{stat.st_size}"
