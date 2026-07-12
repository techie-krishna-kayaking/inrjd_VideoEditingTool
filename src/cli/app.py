"""CLI application factory for the project entrypoint."""

from __future__ import annotations

import typer
from rich.console import Console

from src.config.config_models import Settings
from src.cli.make_videos_command import run_make_videos_command, run_render_final_videos_command
from src.cli.organize_command import run_organizer_command
from src.cli.render_long_videos_command import run_render_long_videos_command
from src.cli.render_long_pictures_command import run_render_long_pictures_command
from src.cli.render_short_videos_command import run_render_short_videos_command
from src.cli.render_shorts_pictures_command import run_render_shorts_pictures_command
from src.cli.review_command import run_review_command
from src.review.models import ReviewFilterOptions


def create_cli(settings: Settings) -> typer.Typer:
    """Create and configure the CLI application instance."""
    app = typer.Typer(help="ISKCON NRJD Video Editor")
    console = Console()

    @app.callback()
    def callback() -> None:
        """Provide root command group context for CLI execution."""

    @app.command("version")
    def version() -> None:
        """Display application and environment version details."""
        console.print(
            f"{settings.project.name} | version={settings.project.version} "
            f"| debug={settings.advanced.debug_mode} | log_level={settings.logging.level}"
        )

    @app.command("organize")
    def organize(
        event: str | None = typer.Option(None, "--event", help="Organize one event only (default: all events)."),
        all_events: bool = typer.Option(False, "--all", help="Deprecated. Batch mode is default when --event is not provided."),
        copy_mode: bool = typer.Option(False, "--copy", help="Force copy mode."),
        move_mode: bool = typer.Option(False, "--move", help="Force move mode."),
        link_mode: bool = typer.Option(False, "--link", help="Force symbolic-link mode."),
    ) -> None:
        """Prepare manual-review workspace from analyzer report metadata."""
        selected_modes = [name for flag, name in ((copy_mode, "copy"), (move_mode, "move"), (link_mode, "link")) if flag]
        if len(selected_modes) > 1:
            raise typer.BadParameter("Use only one of --copy, --move, or --link.")
        mode_override = selected_modes[0] if selected_modes else None

        exit_code = run_organizer_command(
            settings=settings,
            event_name=event,
            all_events=all_events,
            mode_override=mode_override,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("review")
    def review(
        event: str | None = typer.Option(None, "--event", help="Review one event only."),
        media_type: str | None = typer.Option(
            None,
            "--type",
            help="Review one bucket only: shortform_pictures, shortform_videos, longform_pictures, longform_videos.",
        ),
        resume: bool = typer.Option(False, "--resume", help="Resume from saved review progress."),
        all_events: bool = typer.Option(False, "--all", help="Review all events under input/."),
        filter_portrait_images: bool = typer.Option(False, "--filter-portrait-images", help="Review only portrait images."),
        filter_landscape_images: bool = typer.Option(False, "--filter-landscape-images", help="Review only landscape images."),
        filter_videos: bool = typer.Option(False, "--filter-videos", help="Review only videos."),
        filter_low_quality: bool = typer.Option(False, "--filter-low-quality", help="Review only low quality files."),
        filter_duplicates: bool = typer.Option(False, "--filter-duplicates", help="Review only duplicate candidates."),
    ) -> None:
        """Run interactive CLI review before rendering."""
        filters = ReviewFilterOptions(
            portrait_images=filter_portrait_images,
            landscape_images=filter_landscape_images,
            videos=filter_videos,
            low_quality=filter_low_quality,
            duplicates=filter_duplicates,
        )

        exit_code = run_review_command(
            settings=settings,
            event_name=event,
            bucket_type=media_type,
            resume=resume,
            all_events=all_events,
            filters=filters,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("render-shorts-pictures")
    def render_shorts_pictures(
        event: str | None = typer.Option(None, "--event", help="Render one event only."),
    ) -> None:
        """Render automated short-form videos from shortform_pictures folders."""
        exit_code = run_render_shorts_pictures_command(
            settings=settings,
            event_name=event,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("render-long-pictures")
    def render_long_pictures(
        event: str | None = typer.Option(None, "--event", help="Render one event only."),
        profile: str | None = typer.Option(None, "--profile", help="Optional YAML profile name."),
    ) -> None:
        """Render one cinematic long-form picture video per event."""
        exit_code = run_render_long_pictures_command(
            settings=settings,
            event_name=event,
            profile=profile,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("render-short-videos")
    def render_short_videos(
        event: str | None = typer.Option(None, "--event", help="Render one event only."),
        profile: str | None = typer.Option(None, "--profile", help="Optional YAML profile name."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview timeline without ffmpeg rendering."),
    ) -> None:
        """Render short-form outputs from shortform_videos using unified video engine."""
        exit_code = run_render_short_videos_command(
            settings=settings,
            event_name=event,
            profile=profile,
            dry_run=dry_run,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("render-long-videos")
    def render_long_videos(
        event: str | None = typer.Option(None, "--event", help="Render one event only."),
        profile: str | None = typer.Option(None, "--profile", help="Optional YAML profile name."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview timeline without ffmpeg rendering."),
    ) -> None:
        """Render long-form output from longform_videos using unified video engine."""
        exit_code = run_render_long_videos_command(
            settings=settings,
            event_name=event,
            profile=profile,
            dry_run=dry_run,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("make-videos")
    def make_videos(
        event: str | None = typer.Option(None, "--event", help="Render one event only (default: all events in batch)."),
        profile: str | None = typer.Option(None, "--profile", help="Optional YAML profile name for video workflows."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview unified video timelines without ffmpeg rendering."),
    ) -> None:
        """Run one-command pipeline: organize first, then render all 4 outputs per event."""
        exit_code = run_make_videos_command(
            settings=settings,
            event_name=event,
            profile=profile,
            dry_run=dry_run,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    @app.command("render-final-videos")
    def render_final_videos(
        event: str | None = typer.Option(None, "--event", help="Render one event only (default: all events in batch)."),
        profile: str | None = typer.Option(None, "--profile", help="Optional YAML profile name for video workflows."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview unified video timelines without ffmpeg rendering."),
    ) -> None:
        """Step-2 command: render/publish final videos after running organize."""
        exit_code = run_render_final_videos_command(
            settings=settings,
            event_name=event,
            profile=profile,
            dry_run=dry_run,
            console=console,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)

    return app
