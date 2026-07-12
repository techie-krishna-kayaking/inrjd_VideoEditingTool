"""CLI helper for one-command organize + render pipeline per event."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.organizer.exceptions import OrganizerError
from src.organizer.service import MediaOrganizer
from src.renderer.long_pictures_workflow import LongPicturesWorkflow
from src.renderer.shorts_pictures_workflow import ShortsPicturesWorkflow
from src.renderer.unified_video_workflow import UnifiedVideoProcessingEngine


def run_make_videos_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    dry_run: bool,
    console: Console,
) -> int:
    """Run organizer first, then render all four outputs per event in sequence."""
    events = _organize_and_discover_events(settings=settings, event_name=event_name, console=console)
    return _run_render_pipeline(
        settings=settings,
        events=events,
        profile=profile,
        dry_run=dry_run,
        console=console,
        summary_title="Make Videos Summary",
    )


def run_render_final_videos_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    dry_run: bool,
    console: Console,
) -> int:
    """Render/publish pipeline only, assuming organize has already run."""
    events = [event_name] if event_name else _discover_events(settings)
    return _run_render_pipeline(
        settings=settings,
        events=events,
        profile=profile,
        dry_run=dry_run,
        console=console,
        summary_title="Render Final Videos Summary",
    )


def _run_render_pipeline(
    settings: Settings,
    events: list[str],
    profile: str | None,
    dry_run: bool,
    console: Console,
    summary_title: str,
) -> int:
    """Run render and final publish for each event in sequence."""
    if not events:
        console.print("[yellow]No events found under input/. Nothing to render.[/yellow]")
        return 0

    output_root = settings.project_root / settings.paths.output
    output_root.mkdir(parents=True, exist_ok=True)

    shorts_pictures_workflow = ShortsPicturesWorkflow(settings=settings)
    long_pictures_workflow = LongPicturesWorkflow(settings=settings)
    unified_engine = UnifiedVideoProcessingEngine(settings=settings)

    summary: list[tuple[str, str, str, str, str, int]] = []
    overall_failures = 0

    for current_event in events:
        short_pic_result = shorts_pictures_workflow.render(event_name=current_event)
        long_pic_result = long_pictures_workflow.render(event_name=current_event, profile=profile)
        short_video_result = unified_engine.render(
            mode="short",
            event_name=current_event,
            profile=profile,
            dry_run=dry_run,
        )
        long_video_result = unified_engine.render(
            mode="long",
            event_name=current_event,
            profile=profile,
            dry_run=dry_run,
        )

        published_short_pictures = _publish_output(
            source_path=_first_short_picture_output(short_pic_result),
            event_name=current_event,
            video_type="pictures_short",
            output_root=output_root,
        )
        published_long_pictures = _publish_output(
            source_path=_first_long_picture_output(long_pic_result),
            event_name=current_event,
            video_type="pictures_long",
            output_root=output_root,
        )
        published_short_main = _publish_output(
            source_path=_first_unified_output(short_video_result),
            event_name=current_event,
            video_type="short_main",
            output_root=output_root,
        )
        published_long_main = _publish_output(
            source_path=_first_unified_output(long_video_result),
            event_name=current_event,
            video_type="long_main",
            output_root=output_root,
        )

        event_failures = sum(
            1
            for item in (
                published_short_pictures,
                published_long_pictures,
                published_short_main,
                published_long_main,
            )
            if item == "n/a"
        )
        overall_failures += event_failures
        summary.append(
            (
                current_event,
                published_short_pictures,
                published_long_pictures,
                published_short_main,
                published_long_main,
                event_failures,
            )
        )

    table = Table(title=summary_title)
    table.add_column("Event", style="cyan")
    table.add_column("pictures_short", justify="right")
    table.add_column("pictures_long", justify="right")
    table.add_column("short_main", justify="right")
    table.add_column("long_main", justify="right")
    table.add_column("Failures", justify="right", style="red")

    for row in summary:
        table.add_row(
            row[0],
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
        )

    console.print(table)
    return 1 if overall_failures else 0


def _discover_events(settings: Settings) -> list[str]:
    """Discover event folders in input root for batch rendering."""
    input_root = settings.project_root / settings.paths.input
    if not input_root.exists() or not input_root.is_dir():
        return []
    return sorted(item.name for item in input_root.iterdir() if item.is_dir())


def _organize_and_discover_events(settings: Settings, event_name: str | None, console: Console) -> list[str]:
    """Run organizer first, then return event list for rendering."""
    organizer = MediaOrganizer(
        project_root=settings.project_root,
        config_path=settings.config_path,
        input_root=settings.project_root / settings.paths.input,
        reports_root=settings.project_root / settings.paths.reports,
    )

    try:
        run_result = organizer.organize(
            event_name=event_name,
            all_events=event_name is None,
            override_mode=None,
        )
    except (OrganizerError, ValueError) as exc:
        console.print(f"[red]Organizer failed: {exc}[/red]")
        return []

    if event_name:
        return [event_name]

    events = [item.stats.event_name for item in run_result.events]
    return sorted(set(events))


def _first_short_picture_output(results):
    """Pick the first rendered short-picture output for publishing."""
    if not results:
        return None
    rendered = results[0].rendered_files
    if not rendered:
        return None
    return sorted(rendered)[0]


def _first_long_picture_output(results):
    """Pick rendered long-picture output for publishing."""
    if not results:
        return None
    return results[0].output_file


def _first_unified_output(results):
    """Pick the first unified engine output for publishing."""
    if not results:
        return None
    outputs = results[0].outputs
    if not outputs:
        return None
    return sorted(outputs)[0]


def _publish_output(source_path: Path | None, event_name: str, video_type: str, output_root: Path) -> str:
    """Publish final output using <folder_name>_<video_type> naming convention."""
    if source_path is None or not source_path.exists():
        return "n/a"

    suffix = source_path.suffix if source_path.suffix else ".mp4"
    destination = output_root / f"{event_name}_{video_type}{suffix}"
    shutil.copy2(source_path, destination)
    return destination.name
