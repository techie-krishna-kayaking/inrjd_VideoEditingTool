"""Interactive CLI review engine for organized media."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from src.review.discovery import SUPPORTED_BUCKETS, build_review_queue, discover_event_names
from src.review.key_reader import read_key
from src.review.keys import map_key_to_action
from src.review.metadata import estimate_quality_score, orientation_from_dimensions, read_media_dimensions
from src.review.models import (
    EventReviewResult,
    ReviewAction,
    ReviewFilterOptions,
    ReviewProgress,
    ReviewRunConfig,
)
from src.review.progress_store import load_progress, save_progress
from src.review.reporter import write_review_report
from src.review.viewer import open_in_default_viewer


class ReviewEngine:
    """CLI-first review workflow with resume and report persistence."""

    def __init__(
        self,
        config: ReviewRunConfig,
        console: Console,
        key_reader: Callable[[], str] | None = None,
        viewer: Callable[[Path], bool] | None = None,
    ) -> None:
        """Initialize engine with injectable key and viewer adapters."""
        self._config = config
        self._console = console
        self._read_key = key_reader if key_reader is not None else read_key
        self._open_viewer = viewer if viewer is not None else open_in_default_viewer

    def run(
        self,
        event_name: str | None,
        all_events: bool,
        media_type_bucket: str | None,
        resume: bool,
        filters: ReviewFilterOptions,
    ) -> list[EventReviewResult]:
        """Run review workflow across selected events."""
        if media_type_bucket and media_type_bucket not in SUPPORTED_BUCKETS:
            raise ValueError(f"Unsupported --type value: {media_type_bucket}")

        events = discover_event_names(
            input_root=self._config.input_root,
            target_event=event_name,
            all_events=all_events,
        )
        results: list[EventReviewResult] = []

        for current_event in events:
            result = self._run_event(
                event_name=current_event,
                media_type_bucket=media_type_bucket,
                resume=resume,
                filters=filters,
            )
            if result is not None:
                results.append(result)

        return results

    def _run_event(
        self,
        event_name: str,
        media_type_bucket: str | None,
        resume: bool,
        filters: ReviewFilterOptions,
    ) -> EventReviewResult | None:
        """Run review for one event and return summary result."""
        queue = build_review_queue(
            input_root=self._config.input_root,
            event_name=event_name,
            bucket_filter=media_type_bucket,
            filters=filters,
            low_quality_threshold=self._config.low_quality_threshold,
        )

        if not queue:
            self._console.print(f"[yellow]No review candidates for event {event_name}.[/yellow]")
            return None

        event_reports_dir = self._config.input_root / event_name / "reports"
        progress_path = event_reports_dir / self._config.progress_file_name
        report_path = event_reports_dir / self._config.report_file_name
        rejected_dir = self._config.input_root / event_name / "rejected"
        rejected_dir.mkdir(parents=True, exist_ok=True)

        progress_state = load_progress(progress_path) if resume else ReviewProgress()
        if not resume:
            save_progress(progress_path, progress_state)

        started_at = time.perf_counter()
        index = max(0, min(progress_state.current_index, len(queue) - 1))

        while 0 <= index < len(queue):
            item = queue[index]
            item = self._ensure_metadata(item)
            if not item.path.exists() or not item.path.is_file():
                index += 1
                progress_state.current_index = index
                save_progress(progress_path, progress_state)
                continue

            self._display_item(
                item=item,
                position=index + 1,
                total=len(queue),
                progress=progress_state,
                elapsed_seconds=time.perf_counter() - started_at,
            )

            if self._config.open_with_default_viewer:
                opened = self._open_viewer(item.path)
                if not opened:
                    self._console.print(f"[yellow]Could not open file, skipping: {item.path}[/yellow]")
                    action: ReviewAction = "skip"
                else:
                    action = self._read_action()
            else:
                action = self._read_action()

            if action == "quit":
                break

            if action == "back":
                index = max(0, index - 1)
                progress_state.current_index = index
                save_progress(progress_path, progress_state)
                continue

            if action == "next":
                action = "skip"

            if action == "keep":
                _append_unique(progress_state.accepted, str(item.path))
            elif action == "reject":
                destination = _move_to_rejected(item.path, rejected_dir)
                _append_unique(progress_state.rejected, str(destination))
            elif action == "skip":
                _append_unique(progress_state.skipped, str(item.path))

            index += 1
            progress_state.current_index = index
            save_progress(progress_path, progress_state)

        duration_seconds = time.perf_counter() - started_at
        report = write_review_report(
            report_path=report_path,
            event_name=event_name,
            reviewer=self._config.reviewer,
            duration_seconds=duration_seconds,
            progress=progress_state,
        )

        return EventReviewResult(
            event_name=event_name,
            total_items=len(queue),
            reviewed_items=min(progress_state.current_index, len(queue)),
            accepted=len(progress_state.accepted),
            rejected=len(progress_state.rejected),
            skipped=len(progress_state.skipped),
            duration_seconds=duration_seconds,
            report_path=report,
        )

    def _display_item(
        self,
        item,
        position: int,
        total: int,
        progress: ReviewProgress,
        elapsed_seconds: float,
    ) -> None:
        """Render current item metadata and progress indicators."""
        table = Table(title=f"Review | {item.event_name}")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("File Name", item.path.name)
        table.add_row("Media Type", item.media_type)
        resolution = f"{item.width}x{item.height}" if item.width and item.height else "unknown"
        table.add_row("Resolution", resolution)
        table.add_row("Orientation", item.orientation)
        table.add_row("File Size", str(item.size_bytes))
        table.add_row("Quality Score", str(item.quality_score))
        table.add_row("Current Position", f"{position} / {total}")
        self._console.print(table)

        reviewed = min(progress.current_index, total)
        remaining = max(0, total - reviewed)
        speed = reviewed / elapsed_seconds if elapsed_seconds > 0 else 0.0
        eta_seconds = int(remaining / speed) if speed > 0 else int(remaining * self._config.estimated_seconds_per_item)

        stats = Table(title="Review Progress")
        stats.add_column("Metric", style="magenta")
        stats.add_column("Value", style="green")
        stats.add_row("Current File", str(position))
        stats.add_row("Remaining Files", str(remaining))
        stats.add_row("Accepted", str(len(progress.accepted)))
        stats.add_row("Rejected", str(len(progress.rejected)))
        stats.add_row("Skipped", str(len(progress.skipped)))
        stats.add_row("Estimated Remaining Time", f"{eta_seconds}s")
        self._console.print(stats)

        with Progress(
            TextColumn("[bold blue]Progress"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeRemainingColumn(),
            transient=True,
            console=self._console,
        ) as bar:
            task_id = bar.add_task("review", total=total, completed=reviewed)
            bar.update(task_id, completed=reviewed)

        self._console.print("[bold]Actions:[/bold] K=Keep R=Reject S=Skip B=Back N=Next Q=Quit")
        self._console.print("[bold]Shortcuts:[/bold] Arrow keys, Space, Enter, Escape")

    def _ensure_metadata(self, item):
        """Populate dimensions/orientation/quality lazily when unavailable."""
        if item.width is not None and item.height is not None and item.quality_score is not None:
            return item

        width, height = read_media_dimensions(item.path, item.media_type)
        orientation = orientation_from_dimensions(width=width, height=height)
        quality_score = estimate_quality_score(width=width, height=height, size_bytes=item.size_bytes)
        item.width = width
        item.height = height
        item.orientation = orientation
        item.quality_score = quality_score
        return item

    def _read_action(self) -> ReviewAction:
        """Read keys until a known action is received."""
        while True:
            key = self._read_key()
            action = map_key_to_action(key)
            if action is not None:
                return action
            self._console.print("[yellow]Unknown key. Use K/R/S/B/N/Q or arrow/space/enter/esc.[/yellow]")


def _append_unique(items: list[str], value: str) -> None:
    """Append value to list only when not already present."""
    if value not in items:
        items.append(value)


def _move_to_rejected(source_path: Path, rejected_dir: Path) -> Path:
    """Move reviewed file to rejected folder without deleting data."""
    rejected_dir.mkdir(parents=True, exist_ok=True)
    candidate = rejected_dir / source_path.name
    if not candidate.exists():
        shutil.move(str(source_path), str(candidate))
        return candidate

    stem = source_path.stem
    suffix = source_path.suffix
    index = 1
    while True:
        candidate = rejected_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            shutil.move(str(source_path), str(candidate))
            return candidate
        index += 1
