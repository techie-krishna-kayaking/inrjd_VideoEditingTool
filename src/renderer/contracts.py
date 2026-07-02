"""Service contracts for renderer domain."""

from __future__ import annotations

from typing import Protocol

from src.models.entities import RenderJob


class RendererService(Protocol):
    """Contract for renderer implementations."""

    def submit(self, render_job: RenderJob) -> str:
        """Submit a render job and return tracking identifier."""
