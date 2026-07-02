"""Media Organizer implementation for analyzer-driven workspace preparation."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import yaml
from loguru import logger

from src.organizer.analyzer_report import load_analyzer_entries
from src.organizer.models import (
    AnalyzerMediaEntry,
    EventOrganizationResult,
    EventOrganizationStats,
    OrganizerRunResult,
)
from src.organizer.reporter import write_event_reports, write_run_summary
from src.organizer.state import OrganizerState, current_source_fingerprint, load_state, save_state, source_signature
from src.utils.file_utils import ensure_directory


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mts", ".mkv", ".m4v", ".webm"}
DEFAULT_ANALYZER_REPORT = "analyzer_report.json"
DEFAULT_MODE = "copy"
VALID_MODES = {"copy", "move", "link"}


class MediaOrganizer:
    """Organizer service that prepares event review workspaces from analyzer metadata."""

    def __init__(self, project_root: Path, config_path: Path, input_root: Path, reports_root: Path) -> None:
        """Initialize organizer with resolved project and report roots."""
        self._project_root = project_root
        self._config_path = config_path
        self._input_root = input_root
        self._reports_root = reports_root

    def organize(self, event_name: str | None, all_events: bool, override_mode: str | None) -> OrganizerRunResult:
        """Run organization workflow over selected events."""
        started_at = time.perf_counter()
        mode = self._resolve_mode(override_mode=override_mode)
        analyzer_report = self._resolve_analyzer_report_path()

        entries = load_analyzer_entries(analyzer_report)
        grouped = self._group_entries(entries=entries)

        if event_name:
            if event_name not in grouped:
                grouped = {}
            else:
                grouped = {event_name: grouped[event_name]}

        results: list[EventOrganizationResult] = []
        for current_event, event_entries in sorted(grouped.items()):
            results.append(self._organize_event(current_event=current_event, entries=event_entries, mode=mode))

        duration = time.perf_counter() - started_at
        run_result = OrganizerRunResult(mode=mode, duration_seconds=duration, events=results)
        write_run_summary(output_reports_dir=self._reports_root, run_result=run_result)
        return run_result

    def _organize_event(self, current_event: str, entries: list[AnalyzerMediaEntry], mode: str) -> EventOrganizationResult:
        """Organize one event using analyzer metadata only."""
        event_root = ensure_directory(self._input_root / current_event)
        directories = {
            "shortform_pictures": ensure_directory(event_root / "shortform_pictures"),
            "shortform_videos": ensure_directory(event_root / "shortform_videos"),
            "longform_pictures": ensure_directory(event_root / "longform_pictures"),
            "longform_videos": ensure_directory(event_root / "longform_videos"),
            "rejected": ensure_directory(event_root / "rejected"),
            "reports": ensure_directory(event_root / "reports"),
        }

        state_path = directories["reports"] / "organization_state.json"
        state = load_state(state_path)
        stats = EventOrganizationStats(event_name=current_event)
        warnings: list[str] = []
        errors: list[str] = []

        for entry in entries:
            try:
                if not entry.source_path.exists() or not entry.source_path.is_file():
                    stats.rejected += 1
                    stats.skipped += 1
                    warnings.append(f"Missing source file: {entry.source_path}")
                    logger.warning("Skipped missing source file: {}", entry.source_path)
                    continue

                source_path = entry.source_path
                signature = source_signature(entry)
                fingerprint_now = current_source_fingerprint(source_path)
                source_key = str(source_path.resolve())

                prior_source = state.by_source.get(source_key)
                if prior_source and str(prior_source.get("fingerprint", "")) != fingerprint_now:
                    warnings.append(f"Modified file detected and reprocessed: {source_path}")
                    logger.warning("Modified file detected: {}", source_path)

                prior_signature = state.by_signature.get(signature)
                if prior_signature is not None:
                    target_existing = self._project_root / str(prior_signature.get("target_relative", ""))
                    if target_existing.exists():
                        stats.skipped += 1
                        logger.info("Skipped duplicate/renamed file: {}", source_path)
                        continue

                destination_folder = self._destination_folder(entry)
                destination_dir = directories[destination_folder]
                destination_path = self._build_destination_path(source_path=source_path, destination_dir=destination_dir)

                if destination_path.exists() and self._same_file(source_path=source_path, destination_path=destination_path):
                    stats.skipped += 1
                    logger.info("Skipped existing file: {}", destination_path)
                    self._update_state(
                        state=state,
                        signature=signature,
                        source_key=source_key,
                        fingerprint=fingerprint_now,
                        target_relative=destination_path.relative_to(self._project_root),
                        mode=mode,
                    )
                    continue

                operation = self._apply_mode(mode=mode, source_path=source_path, destination_path=destination_path)
                self._update_stats(stats=stats, entry=entry, operation=operation)
                self._update_state(
                    state=state,
                    signature=signature,
                    source_key=source_key,
                    fingerprint=fingerprint_now,
                    target_relative=destination_path.relative_to(self._project_root),
                    mode=mode,
                )

                logger.info("{} file: {} -> {}", operation.capitalize(), source_path, destination_path)
            except Exception as exc:  # noqa: BLE001
                stats.errors += 1
                errors.append(f"{entry.source_path}: {exc}")
                logger.exception("Organizer failed for {}", entry.source_path)

        save_state(state_path=state_path, state=state)
        result = EventOrganizationResult(stats=stats, warnings=warnings, errors=errors)
        write_event_reports(reports_dir=directories["reports"], event_result=result, mode=mode)
        return result

    def _resolve_mode(self, override_mode: str | None) -> str:
        """Resolve operation mode from CLI override or YAML organizer settings."""
        if override_mode:
            mode = override_mode.strip().lower()
            if mode not in VALID_MODES:
                raise ValueError(f"Unsupported organizer mode: {override_mode}")
            return mode

        try:
            payload = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return DEFAULT_MODE

        if not isinstance(payload, dict):
            return DEFAULT_MODE

        organizer = payload.get("organizer")
        if not isinstance(organizer, dict):
            return DEFAULT_MODE

        strategy = organizer.get("copy_strategy")
        if isinstance(strategy, str) and strategy.strip().lower() in VALID_MODES:
            return strategy.strip().lower()

        return DEFAULT_MODE

    def _resolve_analyzer_report_path(self) -> Path:
        """Resolve analyzer report path from YAML, defaulting to output reports folder."""
        default_path = self._reports_root / DEFAULT_ANALYZER_REPORT
        try:
            payload = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default_path

        if not isinstance(payload, dict):
            return default_path

        organizer = payload.get("organizer")
        if not isinstance(organizer, dict):
            return default_path

        configured = organizer.get("analyzer_report")
        if isinstance(configured, str) and configured.strip():
            report_path = Path(configured.strip())
            if report_path.is_absolute():
                return report_path
            return (self._project_root / report_path).resolve()

        return default_path

    def _group_entries(self, entries: list[AnalyzerMediaEntry]) -> dict[str, list[AnalyzerMediaEntry]]:
        """Group analyzer entries by event name."""
        grouped: dict[str, list[AnalyzerMediaEntry]] = {}
        for entry in entries:
            grouped.setdefault(entry.event_name, []).append(entry)
        return grouped

    def _destination_folder(self, entry: AnalyzerMediaEntry) -> str:
        """Map media entry to destination bucket."""
        suffix = entry.source_path.suffix.lower()
        if entry.media_type == "image" and suffix in SUPPORTED_IMAGE_EXTENSIONS:
            if self._is_portrait(entry):
                return "shortform_pictures"
            return "longform_pictures"
        if entry.media_type == "video" and suffix in SUPPORTED_VIDEO_EXTENSIONS:
            if self._is_portrait(entry):
                return "shortform_videos"
            return "longform_videos"
        return "rejected"

    def _is_portrait(self, entry: AnalyzerMediaEntry) -> bool:
        """Treat media as portrait when height is greater or equal to width."""
        if entry.width is None or entry.height is None:
            return False
        return entry.height >= entry.width

    def _build_destination_path(self, source_path: Path, destination_dir: Path) -> Path:
        """Build unique destination path without renaming original source files."""
        candidate = destination_dir / source_path.name
        if not candidate.exists():
            return candidate

        stem = source_path.stem
        suffix = source_path.suffix
        index = 1
        while True:
            candidate = destination_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def _apply_mode(self, mode: str, source_path: Path, destination_path: Path) -> str:
        """Execute copy, move, or symbolic-link mode."""
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            shutil.copy2(source_path, destination_path)
            return "copied"
        if mode == "move":
            shutil.move(str(source_path), str(destination_path))
            return "moved"
        if mode == "link":
            destination_path.symlink_to(source_path.resolve())
            return "linked"
        raise ValueError(f"Unsupported organizer mode: {mode}")

    def _same_file(self, source_path: Path, destination_path: Path) -> bool:
        """Compare source and destination by size and mtime-second granularity."""
        source_stat = source_path.stat()
        destination_stat = destination_path.stat()
        return (
            source_stat.st_size == destination_stat.st_size
            and int(source_stat.st_mtime) == int(destination_stat.st_mtime)
        )

    def _update_stats(self, stats: EventOrganizationStats, entry: AnalyzerMediaEntry, operation: str) -> None:
        """Update counters for classification and operation outcome."""
        folder = self._destination_folder(entry)
        if folder == "shortform_pictures":
            stats.portrait_images += 1
        elif folder == "longform_pictures":
            stats.landscape_images += 1
        elif folder == "shortform_videos":
            stats.portrait_videos += 1
        elif folder == "longform_videos":
            stats.landscape_videos += 1
        else:
            stats.rejected += 1

        if operation == "copied":
            stats.copied += 1
        elif operation == "moved":
            stats.moved += 1
        elif operation == "linked":
            stats.linked += 1

        if entry.size_bytes:
            stats.total_size_bytes += entry.size_bytes

    def _update_state(
        self,
        state: OrganizerState,
        signature: str,
        source_key: str,
        fingerprint: str,
        target_relative: Path,
        mode: str,
    ) -> None:
        """Persist source/signature mapping used for resume and duplicate detection."""
        record = {
            "target_relative": str(target_relative),
            "mode": mode,
            "fingerprint": fingerprint,
        }
        state.by_signature[signature] = record
        state.by_source[source_key] = record
