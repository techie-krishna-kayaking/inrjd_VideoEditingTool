"""CLI command wrapper for short-form source video rendering."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.renderer.unified_video_workflow import UnifiedVideoProcessingEngine


def run_render_short_videos_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    dry_run: bool,
    console: Console,
) -> int:
    """Run unified engine in short mode and print per-event output summary."""
    engine = UnifiedVideoProcessingEngine(settings=settings)
    results = engine.render(mode="short", event_name=event_name, profile=profile, dry_run=dry_run)

    if not results:
        console.print("[yellow]No short-form video outputs were generated.[/yellow]")
        return 0

    table = Table(title="Short Video Render Summary")
    table.add_column("Event", style="cyan")
    table.add_column("Outputs", justify="right", style="green")
    table.add_column("Report", style="blue")

    for result in results:
        table.add_row(result.event_name, str(len(result.outputs)), str(result.report_path))

    console.print(table)
    return 0
