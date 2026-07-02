"""Path-related utility functions."""

from __future__ import annotations

from pathlib import Path


def project_relative_path(project_root: Path, relative_path: str) -> Path:
    """Resolve a normalized project-relative path."""
    return (project_root / relative_path).resolve()
