"""Unit tests for configuration loading, validation, defaults, and errors."""

from __future__ import annotations

import copy
from collections.abc import Callable

from pathlib import Path

import pytest

from src.config.config_loader import DEFAULT_CONFIG
from src.config.config_manager import ConfigManager, ConfigManagerError


ProjectBuilder = Callable[..., tuple[Path, Path]]


def test_config_load_success(project_builder: ProjectBuilder, monkeypatch: pytest.MonkeyPatch) -> None:
    """Load valid config and return a strongly typed settings object."""
    builder = project_builder
    project_root, config_path = builder()
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/tool")
    ConfigManager.reset()

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    assert settings.project.name == "ISKCON NRJD Media Engine"
    assert settings.shorts.resolution.width == 1080
    assert settings.long.duration.default == 360
    assert settings.render.workers == 2


def test_environment_overrides(project_builder: ProjectBuilder, monkeypatch: pytest.MonkeyPatch) -> None:
    """Override output folder, workers, and debug mode from environment variables."""
    builder = project_builder
    project_root, config_path = builder()
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/tool")
    monkeypatch.setenv("NRJD_OUTPUT_FOLDER", "custom_output")
    monkeypatch.setenv("NRJD_WORKERS", "1")
    monkeypatch.setenv("NRJD_DEBUG", "true")
    ConfigManager.reset()

    settings = ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    assert settings.paths.output == "custom_output"
    assert settings.render.workers == 1
    assert settings.advanced.debug_mode is True
    assert settings.logging.level == "DEBUG"


def test_missing_required_sections_raise_error(
    project_builder: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a friendly error when top-level sections are missing."""
    builder = project_builder
    config = copy.deepcopy(DEFAULT_CONFIG)
    del config["audio"]
    project_root, config_path = builder(config_data=config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/tool")
    ConfigManager.reset()

    with pytest.raises(ConfigManagerError) as error:
        ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    assert "Missing required config sections" in str(error.value)


def test_invalid_resolution_raise_error(
    project_builder: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a friendly error for unsupported profile resolution."""
    builder = project_builder
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["shorts"]["resolution"] = {"width": 1000, "height": 1000}
    project_root, config_path = builder(config_data=config)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/tool")
    ConfigManager.reset()

    with pytest.raises(ConfigManagerError) as error:
        ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    assert "Invalid resolution for shorts" in str(error.value)


def test_missing_overlay_raise_error(
    project_builder: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a friendly error when required overlay files are missing."""
    builder = project_builder
    project_root, config_path = builder()
    missing_file = project_root / "assets" / "overlays" / "website.png"
    missing_file.unlink()
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/tool")
    ConfigManager.reset()

    with pytest.raises(ConfigManagerError) as error:
        ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    assert "Missing overlay file for website" in str(error.value)


def test_missing_ffmpeg_raise_error(
    project_builder: ProjectBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise a friendly error when FFmpeg is unavailable."""
    builder = project_builder
    project_root, config_path = builder()

    def _which(program: str) -> str | None:
        if program in {"ffmpeg", "ffprobe"}:
            return None
        return "/usr/local/bin/tool"

    monkeypatch.setattr("shutil.which", _which)
    ConfigManager.reset()

    with pytest.raises(ConfigManagerError) as error:
        ConfigManager.load(config_path=config_path, project_root=project_root, force_reload=True)

    assert "Missing FFmpeg" in str(error.value)
