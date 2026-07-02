"""Unit tests for short-form picture rendering workflow."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image

from src.config.config_manager import ConfigManager
from src.renderer.shorts_pictures_workflow import ShortsPicturesWorkflow


def _write_image(path: Path, width: int = 1080, height: int = 1920) -> None:
    """Create a valid portrait test image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), color=(140, 120, 110))
    image.save(path)


def _write_music(path: Path) -> None:
    """Write placeholder audio file bytes for workflow selection tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-music")


def _touch_overlays(project_root: Path) -> None:
    """Create required overlay and font assets used by workflow."""
    overlays = project_root / "assets" / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    for name in ("shorts_header.png", "shorts_footer.png", "socials.png", "website.png"):
        _write_image(overlays / name, width=1080, height=240)

    fonts = project_root / "assets" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    # Reuse an existing system-like placeholder path expectation.
    (fonts / "default.ttf").write_bytes(b"placeholder-font")

    music_dir = project_root / "assets" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)


def _mock_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Mock ffmpeg command execution as successful."""
    return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


def test_render_shorts_pictures_generates_multiple_parts(tmp_path: Path) -> None:
    """Workflow should generate multiple parts and write JSON report when enough images exist."""
    builder_root = tmp_path / "project"
    config_path = builder_root / "config" / "config.yaml"
    _touch_overlays(builder_root)

    music_dir = builder_root / "assets" / "music"
    _write_music(music_dir / "track01.mp3")

    event_name = "2026-Feb-Gaura Purnima"
    source_dir = builder_root / "input" / event_name / "shortform_pictures"
    for index in range(85):
        _write_image(source_dir / f"img_{index:03d}.jpg")

    # Build a complete config by copying project default and adjusting roots for tmp project.
    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=builder_root, force_reload=True)

    workflow = ShortsPicturesWorkflow(
        settings=settings,
        command_runner=_mock_runner,
        random_seed=123,
    )
    results = workflow.render(event_name=event_name)

    assert len(results) == 1
    result = results[0]
    assert len(result.rendered_files) == 3

    expected_names = {
        f"{event_name}-short-picture-part01.mp4",
        f"{event_name}-short-picture-part02.mp4",
        f"{event_name}-short-picture-part03.mp4",
    }
    assert {path.name for path in result.rendered_files} == expected_names

    report_payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report_payload["event_name"] == event_name
    assert len(report_payload["parts"]) == 3


def test_render_shorts_pictures_skips_event_without_images(tmp_path: Path) -> None:
    """Workflow should skip event when no source images exist."""
    builder_root = tmp_path / "project"
    config_path = builder_root / "config" / "config.yaml"
    _touch_overlays(builder_root)

    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=builder_root, force_reload=True)

    workflow = ShortsPicturesWorkflow(settings=settings, command_runner=_mock_runner, random_seed=99)
    results = workflow.render(event_name="2026-Apr-Ram Navami")

    assert results == []
