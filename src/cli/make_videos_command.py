"""CLI helper for one-command organize + render pipeline per event."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
import tempfile

import yaml
from PIL import Image, ImageOps
from rich.console import Console
from rich.table import Table

from src.config.config_models import Settings
from src.organizer.exceptions import OrganizerError
from src.organizer.service import MediaOrganizer
from src.renderer.long_pictures_workflow import LongPicturesWorkflow
from src.renderer.shorts_pictures_workflow import ShortsPicturesWorkflow
from src.renderer.unified_video_workflow import UnifiedVideoProcessingEngine


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mts", ".mkv", ".m4v", ".webm"}


def run_make_videos_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    dry_run: bool,
    keep_intermediate: bool,
    console: Console,
) -> int:
    """Run organizer first, then render all four outputs per event in sequence."""
    events = _organize_and_discover_events(settings=settings, event_name=event_name, console=console)
    return _run_render_pipeline(
        settings=settings,
        events=events,
        profile=profile,
        dry_run=dry_run,
        keep_intermediate=keep_intermediate,
        console=console,
        summary_title="Make Videos Summary",
    )


def run_render_final_videos_command(
    settings: Settings,
    event_name: str | None,
    profile: str | None,
    dry_run: bool,
    keep_intermediate: bool,
    console: Console,
) -> int:
    """Render/publish pipeline only, assuming organize has already run."""
    events = [event_name] if event_name else _discover_events(settings)
    return _run_render_pipeline(
        settings=settings,
        events=events,
        profile=profile,
        dry_run=dry_run,
        keep_intermediate=keep_intermediate,
        console=console,
        summary_title="Render Final Videos Summary",
    )


def _run_render_pipeline(
    settings: Settings,
    events: list[str],
    profile: str | None,
    dry_run: bool,
    keep_intermediate: bool,
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
    try:
        for current_event in events:
            short_pic_result = _render_short_pictures_with_fallback(
                workflow=shorts_pictures_workflow,
                settings=settings,
                event_name=current_event,
            )
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
    finally:
        if not keep_intermediate:
            _cleanup_intermediate_outputs(settings=settings, events=events)


def _cleanup_intermediate_outputs(settings: Settings, events: list[str]) -> None:
    """Remove intermediate folders so output keeps only final root MP4 files."""
    output_root = settings.project_root / settings.paths.output

    for event_name in events:
        shutil.rmtree(output_root / "shorts" / event_name, ignore_errors=True)
        shutil.rmtree(output_root / "long" / event_name, ignore_errors=True)
        thumbnail = output_root / "thumbnails" / f"{event_name}-thumbnail.jpg"
        try:
            thumbnail.unlink(missing_ok=True)
        except Exception:
            pass

    for folder_name in ("shorts", "long", "thumbnails", "logs", "reports", "temp", "failed"):
        shutil.rmtree(output_root / folder_name, ignore_errors=True)

    try:
        (output_root / ".DS_Store").unlink(missing_ok=True)
    except Exception:
        pass


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
        message = str(exc)
        if "before organizing" in message.lower():
            generated = _generate_analyzer_report_from_raw_data(settings=settings, event_name=event_name, console=console)
            if generated:
                try:
                    run_result = organizer.organize(
                        event_name=event_name,
                        all_events=event_name is None,
                        override_mode=None,
                    )
                except (OrganizerError, ValueError) as retry_exc:
                    console.print(f"[red]Organizer failed: {retry_exc}[/red]")
                    return []
            else:
                return []
        else:
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
    destination = output_root / f"{event_name}_{video_type}.mp4"
    if source_path is None or not source_path.exists():
        try:
            destination.unlink(missing_ok=True)
        except Exception:
            pass
        return "n/a"

    suffix = source_path.suffix if source_path.suffix else ".mp4"
    destination = output_root / f"{event_name}_{video_type}{suffix}"
    shutil.copy2(source_path, destination)
    return destination.name


def _generate_analyzer_report_from_raw_data(settings: Settings, event_name: str | None, console: Console) -> bool:
    """Generate minimal analyzer report from raw_data folder for organizer input."""
    raw_root = settings.project_root / settings.paths.raw_data
    if not raw_root.exists() or not raw_root.is_dir():
        console.print(f"[red]Missing raw_data folder: {raw_root}[/red]")
        return False

    target_events = [event_name] if event_name else sorted(item.name for item in raw_root.iterdir() if item.is_dir())
    if not target_events:
        console.print("[yellow]No event folders found in raw_data.[/yellow]")
        return False

    media_records: list[dict[str, object]] = []

    for current_event in target_events:
        event_dir = raw_root / current_event
        if not event_dir.exists() or not event_dir.is_dir():
            continue
        for source in sorted(path for path in event_dir.rglob("*") if path.is_file()):
            if _is_hidden_path(source, root=event_dir):
                continue

            suffix = source.suffix.lower()
            media_type: str | None = None
            if suffix in _IMAGE_EXTENSIONS:
                media_type = "image"
            elif suffix in _VIDEO_EXTENSIONS:
                media_type = "video"
            if media_type is None:
                continue

            width, height = _media_dimensions(path=source, media_type=media_type)
            media_records.append(
                {
                    "event_name": current_event,
                    "source_path": str(source.resolve()),
                    "media_type": media_type,
                    "width": width,
                    "height": height,
                    "size_bytes": source.stat().st_size,
                    "mtime": source.stat().st_mtime,
                }
            )

    if not media_records:
        console.print("[yellow]No supported media files found in raw_data.[/yellow]")
        return False

    report_path = _resolve_analyzer_report_path(settings)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "make-videos-auto-analyzer",
        "media": media_records,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"[green]Generated analyzer report from raw_data: {report_path}[/green]")
    return True


def _resolve_analyzer_report_path(settings: Settings) -> Path:
    """Resolve analyzer report path from config, with default fallback."""
    default_path = settings.project_root / settings.paths.reports / "analyzer_report.json"
    try:
        payload = yaml.safe_load(settings.config_path.read_text(encoding="utf-8"))
    except Exception:
        return default_path

    if not isinstance(payload, dict):
        return default_path
    organizer = payload.get("organizer")
    if not isinstance(organizer, dict):
        return default_path

    configured = organizer.get("analyzer_report")
    if isinstance(configured, str) and configured.strip():
        path = Path(configured.strip())
        if path.is_absolute():
            return path
        return (settings.project_root / path).resolve()
    return default_path


def _media_dimensions(path: Path, media_type: str) -> tuple[int | None, int | None]:
    """Read width/height for image/video; return (None, None) on failure."""
    if media_type == "image":
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened)
                width, height = image.size
            return int(width), int(height)
        except Exception:
            return None, None

    if media_type == "video":
        # Prefer ffprobe because it can account for rotation metadata.
        probed = _video_dimensions_with_rotation(path)
        if probed != (None, None):
            return probed

        try:
            import cv2

            capture = cv2.VideoCapture(str(path))
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            capture.release()
            if width > 0 and height > 0:
                return width, height
        except Exception:
            return None, None

    return None, None


def _video_dimensions_with_rotation(path: Path) -> tuple[int | None, int | None]:
    """Read video dimensions and apply metadata rotation when available."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return None, None
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        return None, None

    streams = payload.get("streams")
    if not isinstance(streams, list):
        return None, None

    stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), None)
    if not isinstance(stream, dict):
        return None, None

    width = int(stream.get("width", 0) or 0)
    height = int(stream.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        return None, None

    rotation = _read_rotation(stream)
    if rotation in {90, 270}:
        width, height = height, width
    return width, height


def _read_rotation(video_stream: dict) -> int:
    """Extract normalized rotation from ffprobe stream payload."""
    tags = video_stream.get("tags") if isinstance(video_stream.get("tags"), dict) else {}
    side_data = video_stream.get("side_data_list") if isinstance(video_stream.get("side_data_list"), list) else []

    values: list[int] = []
    raw_tag = tags.get("rotate")
    if raw_tag is not None:
        try:
            values.append(int(float(str(raw_tag).strip())))
        except Exception:
            pass

    for item in side_data:
        if not isinstance(item, dict):
            continue
        raw_side = item.get("rotation")
        if raw_side is None:
            continue
        try:
            values.append(int(float(str(raw_side).strip())))
        except Exception:
            continue

    if not values:
        return 0

    value = values[-1] % 360
    if value < 0:
        value += 360
    return value


def _is_hidden_path(path: Path, root: Path) -> bool:
    """Return True when file is hidden relative to event root."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return any(part.startswith(".") for part in relative.parts)


def _render_short_pictures_with_fallback(
    workflow: ShortsPicturesWorkflow,
    settings: Settings,
    event_name: str,
) -> list:
    """Render short pictures with fallback to longform_pictures when needed."""
    result = workflow.render(event_name=event_name)
    if result:
        return result

    event_root = settings.project_root / settings.paths.input / event_name
    short_dir = event_root / "shortform_pictures"
    long_dir = event_root / "longform_pictures"

    has_short_images = short_dir.exists() and any(path.is_file() for path in short_dir.iterdir())
    if has_short_images:
        return result

    if not long_dir.exists() or not long_dir.is_dir():
        return result

    long_images = [path for path in sorted(long_dir.iterdir()) if path.is_file()]
    if not long_images:
        return result

    # Keep shorts portrait-first: only use portrait longform images for fallback.
    portrait_fallback_images = [path for path in long_images if _is_portrait_image(path)]
    if not portrait_fallback_images:
        return result

    short_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shortform_fallback_"):
        copied_paths: list[Path] = []
        for source in portrait_fallback_images:
            destination = short_dir / source.name
            if destination.exists():
                continue
            shutil.copy2(source, destination)
            copied_paths.append(destination)

        retried = workflow.render(event_name=event_name)

        for item in copied_paths:
            try:
                item.unlink(missing_ok=True)
            except Exception:
                continue

    return retried


def _is_portrait_image(path: Path) -> bool:
    """Return True when image is portrait-oriented (height greater than width)."""
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened)
            width, height = image.size
        return bool(height > width)
    except Exception:
        return False
