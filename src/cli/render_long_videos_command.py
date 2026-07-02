"""CLI command wrapper for long-form source video rendering."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.renderer.unified_video_workflow import UnifiedVideoProcessingEngine


def run_render_long_videos_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    dry_run: bool,
    console: Console,
) -> int:
    """Run unified engine in long mode and print per-event output summary."""
    engine = UnifiedVideoProcessingEngine(settings=settings)
    results = engine.render(mode="long", event_name=event_name, profile=profile, dry_run=dry_run)

    if not results:
        console.print("[yellow]No long-form video outputs were generated.[/yellow]")
        return 0

    table = Table(title="Long Video Render Summary")
    table.add_column("Event", style="cyan")
    table.add_column("Output", style="green")
    table.add_column("Thumbnail", style="magenta")
    table.add_column("Report", style="blue")

    for result in results:
        output_value = str(result.outputs[0]) if result.outputs else "n/a"
        thumb_value = str(result.thumbnail_path) if result.thumbnail_path else "n/a"
        table.add_row(result.event_name, output_value, thumb_value, str(result.report_path))

    console.print(table)
    return 0
