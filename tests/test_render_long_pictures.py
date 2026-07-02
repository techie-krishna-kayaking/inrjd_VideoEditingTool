"""Unit tests for long-form picture rendering workflow."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image

from src.config.config_manager import ConfigManager
from src.renderer.long_pictures_workflow import LongPicturesWorkflow


def _write_image(path: Path, width: int = 1920, height: int = 1080) -> None:
    """Create a valid landscape test image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), color=(110, 120, 140))
    image.save(path)


def _write_music(path: Path) -> None:
    """Write placeholder audio file bytes for workflow selection tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-music")


def _touch_assets(project_root: Path) -> None:
    """Create required overlays and font assets used by workflow and config validation."""
    overlays = project_root / "assets" / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    for name in ("shorts_header.png", "shorts_footer.png", "socials.png", "website.png"):
        _write_image(overlays / name, width=640, height=120)

    fonts = project_root / "assets" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "default.ttf").write_bytes(b"placeholder-font")

    music_dir = project_root / "assets" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)


def _mock_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Mock ffmpeg/ffprobe command execution with deterministic output."""
    if command and command[0] == "ffprobe":
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="180.0\n", stderr="")
    return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


def test_render_long_pictures_generates_single_output_and_report(tmp_path: Path) -> None:
    """Workflow should generate one long picture video per event and write report/thumbnail."""
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "config.yaml"

    _touch_assets(project_root)
    _write_music(project_root / "assets" / "music" / "track01.mp3")

    event_name = "2026-Feb-Gaura Purnima"
    source_dir = project_root / "input" / event_name / "longform_pictures"
    for index in range(24):
        _write_image(source_dir / f"img_{index:03d}.jpg")

    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    workflow = LongPicturesWorkflow(settings=settings, command_runner=_mock_runner, random_seed=14)
    results = workflow.render(event_name=event_name)

    assert len(results) == 1
    result = results[0]

    assert result.output_file.name == f"{event_name}-long-pictures.mp4"
    assert result.thumbnail_path.name == f"{event_name}-thumbnail.jpg"
    assert result.report_path.name == "long_pictures_report.json"

    assert result.thumbnail_path.exists()
    assert result.report_path.exists()

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["event_name"] == event_name
    assert payload["image_order_mode"] in {"chronological_exif", "chronological", "original", "random"}
    assert isinstance(payload["music_tracks_used"], list)
    assert isinstance(payload["transitions"], list)


def test_render_long_pictures_skips_event_without_images(tmp_path: Path) -> None:
    """Workflow should skip event when no long-form source images exist."""
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "config.yaml"

    _touch_assets(project_root)

    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    workflow = LongPicturesWorkflow(settings=settings, command_runner=_mock_runner, random_seed=9)
    results = workflow.render(event_name="2026-Apr-Ram Navami")

    assert results == []
