"""CLI wiring for interactive review engine."""

from __future__ import annotations

import getpass

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.review.engine import ReviewEngine
from src.review.models import ReviewFilterOptions, ReviewRunConfig


def run_review_command(
    settings: Settings,
    event_name: str | None,
    bucket_type: str | None,
    resume: bool,
    all_events: bool,
    filters: ReviewFilterOptions,
    console: Console,
) -> int:
    """Execute review workflow and print event-level summaries."""
    reviewer = settings.review.reviewer.strip() or getpass.getuser()
    run_config = ReviewRunConfig(
        input_root=settings.project_root / settings.paths.input,
        reviewer=reviewer,
        open_with_default_viewer=settings.review.open_with_default_viewer,
        low_quality_threshold=settings.review.low_quality_threshold,
        estimated_seconds_per_item=settings.review.estimated_seconds_per_item,
        progress_file_name=settings.review.progress_file,
        report_file_name=settings.review.report_file,
    )

    engine = ReviewEngine(config=run_config, console=console)
    results = engine.run(
        event_name=event_name,
        all_events=all_events,
        media_type_bucket=bucket_type,
        resume=resume,
        filters=filters,
    )

    if not results:
        console.print("[yellow]No review sessions were executed.[/yellow]")
        return 0

    summary = Table(title="Review Summary")
    summary.add_column("Event", style="cyan")
    summary.add_column("Reviewed", justify="right", style="green")
    summary.add_column("Accepted", justify="right", style="green")
    summary.add_column("Rejected", justify="right", style="red")
    summary.add_column("Skipped", justify="right", style="yellow")
    summary.add_column("Duration(s)", justify="right", style="magenta")
    summary.add_column("Report", style="blue")

    for result in results:
        summary.add_row(
            result.event_name,
            f"{result.reviewed_items}/{result.total_items}",
            str(result.accepted),
            str(result.rejected),
            str(result.skipped),
            f"{result.duration_seconds:.2f}",
            str(result.report_path),
        )

    console.print(summary)
    return 0
