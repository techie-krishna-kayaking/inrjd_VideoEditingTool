"""Report writer contracts."""

from __future__ import annotations

from typing import Protocol

from src.models.entities import Report


class ReportWriter(Protocol):
    """Contract for report persistence services."""

    def write(self, report: Report) -> str:
        """Persist a report and return output location."""
