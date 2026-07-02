"""Tests for unified video processing engine (short + long modes)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from src.config.config_manager import ConfigManager
from src.renderer.unified_video_workflow import UnifiedVideoProcessingEngine


def _write_project_assets(project_root: Path) -> None:
    """Create required asset files for config validation and overlays."""
    overlays = project_root / "assets" / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    for name in ("shorts_header.png", "shorts_footer.png", "socials.png", "website.png"):
        (overlays / name).write_bytes(b"overlay")

    fonts = project_root / "assets" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "default.ttf").write_bytes(b"font")

    music = project_root / "assets" / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "track01.mp3").write_bytes(b"music")


def _write_video_stub(path: Path) -> None:
    """Create placeholder video file path used by mocked ffprobe/ffmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"video")


def _mock_runner_factory(metadata_by_file: dict[str, dict[str, Any]]):
    """Build deterministic ffprobe/ffmpeg command mock."""

    def _runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        if not command:
            return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="empty")

        executable = command[0]

        if executable == "ffprobe":
            target = Path(command[-1]).name
            if "-print_format" in command:
                data = metadata_by_file.get(target)
                if data is None:
                    return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="probe-failed")
                payload = {
                    "streams": [
                        {
                            "codec_type": "video",
                            "width": data["width"],
                            "height": data["height"],
                            "codec_name": data.get("codec", "h264"),
                            "r_frame_rate": data.get("fps", "30/1"),
                            "tags": {"rotate": str(data.get("rotation", 0))},
                        }
                    ],
                    "format": {
                        "duration": str(data["duration"]),
                        "bit_rate": str(data.get("bitrate", 1800000)),
                    },
                }
                if data.get("audio", True):
                    payload["streams"].append({"codec_type": "audio", "codec_name": "aac"})
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout=json.dumps(payload),
                    stderr="",
                )

            return subprocess.CompletedProcess(args=command, returncode=0, stdout="220.0\n", stderr="")

        if executable == "ffmpeg":
            output_path = Path(command[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"rendered")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    return _runner


def test_render_short_videos_generates_parts_and_clip_usage(tmp_path: Path) -> None:
    """Short mode should create part outputs and persist clip usage memory."""
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "config.yaml"

    _write_project_assets(project_root)

    event_name = "2026-Jun-Ratha Yatra"
    short_dir = project_root / "input" / event_name / "shortform_videos"
    for name in ("video1.mp4", "video2.mp4", "video3.mp4", "video4.mp4", "broken.mp4"):
        _write_video_stub(short_dir / name)

    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    metadata = {
        "video1.mp4": {"width": 1920, "height": 1080, "duration": 26.0, "audio": True},
        "video2.mp4": {"width": 1080, "height": 1920, "duration": 31.0, "audio": True},
        "video3.mp4": {"width": 1920, "height": 1080, "duration": 24.0, "audio": True},
        "video4.mp4": {"width": 1080, "height": 1920, "duration": 29.0, "audio": True},
    }

    workflow = UnifiedVideoProcessingEngine(
        settings=settings,
        command_runner=_mock_runner_factory(metadata),
        random_seed=19,
    )
    results = workflow.render(mode="short", event_name=event_name, dry_run=False)

    assert len(results) == 1
    result = results[0]
    assert result.mode == "short"
    assert result.outputs
    assert result.outputs[0].name.endswith("-short-video-part01.mp4")
    assert all(path.exists() for path in result.outputs)

    clip_usage_path = project_root / "output" / "reports" / "clip_usage.json"
    assert clip_usage_path.exists()
    clip_usage = json.loads(clip_usage_path.read_text(encoding="utf-8"))
    assert isinstance(clip_usage.get("clips"), dict)
    assert len(clip_usage["clips"]) > 0

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "short"
    assert isinstance(report["videos_used"], list)
    assert report["videos_used"]
    assert (project_root / "output" / "reports" / "render_report.csv").exists()
    assert (project_root / "output" / "reports" / "render_report.txt").exists()

    media_usage = json.loads((project_root / "output" / "reports" / "media_usage.json").read_text(encoding="utf-8"))
    assert isinstance(media_usage.get("media"), dict)
    assert media_usage["media"]

    render_history = json.loads((project_root / "output" / "reports" / "render_history.json").read_text(encoding="utf-8"))
    assert isinstance(render_history.get("history"), list)
    assert render_history["history"]

    first_positions = report["outputs"][0]["clip_positions"]
    for index in range(1, len(first_positions)):
        assert first_positions[index]["source"] != first_positions[index - 1]["source"]


def test_render_long_videos_creates_single_output_and_thumbnail(tmp_path: Path) -> None:
    """Long mode should generate exactly one output video and a thumbnail."""
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "config.yaml"

    _write_project_assets(project_root)

    event_name = "2026-Jul-Guru Purnima"
    long_dir = project_root / "input" / event_name / "longform_videos"
    for name in ("long01.mp4", "long02.mp4", "long03.mp4"):
        _write_video_stub(long_dir / name)

    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    metadata = {
        "long01.mp4": {"width": 1920, "height": 1080, "duration": 110.0, "audio": True},
        "long02.mp4": {"width": 1920, "height": 1080, "duration": 95.0, "audio": True},
        "long03.mp4": {"width": 1920, "height": 1080, "duration": 140.0, "audio": True},
    }

    workflow = UnifiedVideoProcessingEngine(
        settings=settings,
        command_runner=_mock_runner_factory(metadata),
        random_seed=23,
    )
    results = workflow.render(mode="long", event_name=event_name, dry_run=False)

    assert len(results) == 1
    result = results[0]
    assert result.mode == "long"
    assert len(result.outputs) == 1
    assert result.outputs[0].name == f"{event_name}-long-video.mp4"
    assert result.outputs[0].exists()

    assert result.thumbnail_path is not None
    assert result.thumbnail_path.name == f"{event_name}-thumbnail.jpg"
    assert result.thumbnail_path.exists()

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "long"
    assert report["thumbnail"] is not None
    assert len(report["outputs"]) == 1


def test_render_short_videos_failed_job_recovery_continues(tmp_path: Path) -> None:
    """Renderer should retry once, persist failed job, and continue remaining parts."""
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "config.yaml"

    _write_project_assets(project_root)

    event_name = "2026-Aug-Janmashtami"
    short_dir = project_root / "input" / event_name / "shortform_videos"
    for name in ("s1.mp4", "s2.mp4", "s3.mp4", "s4.mp4"):
        _write_video_stub(short_dir / name)

    default_config = Path("config/config.yaml").read_text(encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    metadata = {
        "s1.mp4": {"width": 1080, "height": 1920, "duration": 85.0, "audio": True},
        "s2.mp4": {"width": 1080, "height": 1920, "duration": 88.0, "audio": True},
        "s3.mp4": {"width": 1080, "height": 1920, "duration": 91.0, "audio": True},
        "s4.mp4": {"width": 1080, "height": 1920, "duration": 76.0, "audio": True},
    }

    failure_counter = {"part01": 0}

    def flaky_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        if not command:
            return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="empty")

        if command[0] == "ffprobe":
            return _mock_runner_factory(metadata)(command)

        if command[0] == "ffmpeg":
            output_path = Path(command[-1])
            if output_path.name.endswith("part01.mp4"):
                failure_counter["part01"] += 1
                return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="intentional")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"rendered")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    workflow = UnifiedVideoProcessingEngine(settings=settings, command_runner=flaky_runner, random_seed=101)
    results = workflow.render(mode="short", event_name=event_name, dry_run=False)

    assert len(results) == 1
    result = results[0]
    report = json.loads(result.report_path.read_text(encoding="utf-8"))

    assert failure_counter["part01"] >= 2
    assert report["failed_jobs"]
    assert (project_root / "output" / "failed").exists()
