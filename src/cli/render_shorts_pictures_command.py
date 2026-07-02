"""CLI command wrapper for short-form picture rendering workflow."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.renderer.shorts_pictures_workflow import ShortsPicturesWorkflow


def run_render_shorts_pictures_command(
    settings: Settings,
    event_name: str | None,
    console: Console,
) -> int:
    """Run picture-only short rendering workflow and print summary table."""
    workflow = ShortsPicturesWorkflow(settings=settings)
    results = workflow.render(event_name=event_name)

    if not results:
        console.print("[yellow]No short-form picture outputs were generated.[/yellow]")
        return 0

    table = Table(title="Shorts Picture Render Summary")
    table.add_column("Event", style="cyan")
    table.add_column("Files", justify="right", style="green")
    table.add_column("Report", style="blue")

    for result in results:
        table.add_row(result.event_name, str(len(result.rendered_files)), str(result.report_path))

    console.print(table)
    return 0
