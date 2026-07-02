"""Validation utility functions used across bootstrapping code."""

from __future__ import annotations

from pathlib import Path


def validate_file_exists(path: Path) -> None:
    """Validate that a file exists and raise FileNotFoundError otherwise."""
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
