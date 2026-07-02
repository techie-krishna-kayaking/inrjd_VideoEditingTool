"""Shared pytest fixtures for configuration-system tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.config.config_loader import DEFAULT_CONFIG


@pytest.fixture()
def project_builder(tmp_path: Path) -> Any:
	"""Create isolated project structures for configuration tests."""

	def _build(config_data: dict[str, Any] | None = None) -> tuple[Path, Path]:
		project_root = tmp_path / "project"
		config_dir = project_root / "config"
		assets_overlays = project_root / "assets" / "overlays"
		music_dir = project_root / "assets" / "music"
		raw_data = project_root / "raw_data"
		input_dir = project_root / "input"
		output_dir = project_root / "output"

		config_dir.mkdir(parents=True, exist_ok=True)
		assets_overlays.mkdir(parents=True, exist_ok=True)
		music_dir.mkdir(parents=True, exist_ok=True)
		raw_data.mkdir(parents=True, exist_ok=True)
		input_dir.mkdir(parents=True, exist_ok=True)
		output_dir.mkdir(parents=True, exist_ok=True)

		for name in ["shorts_header.png", "shorts_footer.png", "socials.png", "website.png"]:
			(assets_overlays / name).write_bytes(b"overlay")

		to_write = config_data if config_data is not None else DEFAULT_CONFIG
		config_path = config_dir / "config.yaml"
		config_path.write_text(yaml.safe_dump(to_write, sort_keys=False), encoding="utf-8")
		return project_root, config_path

	return _build
