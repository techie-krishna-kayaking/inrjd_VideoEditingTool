"""CLI helpers for media organization command."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.organizer.exceptions import OrganizerError
from src.organizer.models import OrganizerRunResult
from src.organizer.service import MediaOrganizer


def run_organizer_command(
    settings: Settings,
    event_name: str | None,
    all_events: bool,
    mode_override: str | None,
    console: Console,
) -> int:
    """Execute organizer workflow and print rich terminal output."""
    organizer = MediaOrganizer(
        project_root=settings.project_root,
        config_path=settings.config_path,
        input_root=settings.project_root / settings.paths.input,
        reports_root=settings.project_root / settings.paths.reports,
    )

    try:
        result = organizer.organize(
            event_name=event_name,
            all_events=all_events,
            override_mode=mode_override,
        )
    except OrganizerError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    _print_summary(result=result, console=console)
    return 0


def _print_summary(result: OrganizerRunResult, console: Console) -> None:
    """Render event summaries and totals in Rich tables."""
    if not result.events:
        console.print("[yellow]No events found in analyzer report for requested selection.[/yellow]")
        return

    for event_result in result.events:
        stats = event_result.stats
        table = Table(title=f"Organizing | {stats.event_name}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="green")
        table.add_row("Portrait Pictures", str(stats.portrait_images))
        table.add_row("Landscape Pictures", str(stats.landscape_images))
        table.add_row("Portrait Videos", str(stats.portrait_videos))
        table.add_row("Landscape Videos", str(stats.landscape_videos))
        table.add_row("Rejected", str(stats.rejected))
        table.add_row("Total Copied", str(stats.copied))
        table.add_row("Total Linked", str(stats.linked))
        table.add_row("Skipped", str(stats.skipped))
        table.add_row("Errors", str(stats.errors))
        table.add_row("Completed", "yes" if stats.errors == 0 else "with errors")
        console.print(table)

    total = Table(title="Organizer Totals")
    total.add_column("Metric", style="magenta")
    total.add_column("Value", justify="right", style="green")
    total.add_row("Events", str(len(result.events)))
    total.add_row("Duration Seconds", f"{result.duration_seconds:.2f}")
    total.add_row("Mode", result.mode)
    total.add_row("Total Copied", str(sum(item.stats.copied for item in result.events)))
    total.add_row("Total Linked", str(sum(item.stats.linked for item in result.events)))
    total.add_row("Total Rejected", str(sum(item.stats.rejected for item in result.events)))
    total.add_row("Total Size", str(sum(item.stats.total_size_bytes for item in result.events)))
    console.print(total)
