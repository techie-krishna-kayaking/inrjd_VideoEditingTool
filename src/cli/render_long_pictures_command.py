"""CLI command wrapper for long-form picture rendering workflow."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.renderer.long_pictures_workflow import LongPicturesWorkflow


def run_render_long_pictures_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    console: Console,
) -> int:
    """Run long-form picture rendering workflow and print summary table."""
    workflow = LongPicturesWorkflow(settings=settings)
    results = workflow.render(event_name=event_name, profile=profile)

    if not results:
        console.print("[yellow]No long-form picture outputs were generated.[/yellow]")
        return 0

    table = Table(title="Long Picture Render Summary")
    table.add_column("Event", style="cyan")
    table.add_column("Output", style="green")
    table.add_column("Thumbnail", style="magenta")
    table.add_column("Report", style="blue")

    for result in results:
        table.add_row(result.event_name, str(result.output_file), str(result.thumbnail_path), str(result.report_path))

    console.print(table)
    return 0
