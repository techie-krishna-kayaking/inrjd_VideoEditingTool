"""Core dataclasses shared by application layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


@dataclass(slots=True)
class Project:
    """Project metadata and root location details."""

    name: str
    version: str
    root_path: Path
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass(slots=True)
class MediaFile:
    """Normalized media file metadata contract for future pipelines."""

    path: Path
    media_type: str
    size_bytes: int
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RenderJob:
    """Render job descriptor used by orchestration layers."""

    job_id: str
    project_name: str
    created_at: datetime
    status: str
    requested_by: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Report:
    """Report descriptor for generated run outputs."""

    report_id: str
    generated_at: datetime
    format: str
    file_path: Path
    summary: str


@dataclass(slots=True)
class Settings:
    """Runtime settings loaded directly from YAML configuration."""

    config_path: Path
    project_name: str
    environment: str
    log_level: str
    log_directory: str
    data: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, config_path: Path, data: Mapping[str, Any]) -> "Settings":
        """Build settings from raw YAML mapping without schema parsing."""
        project = data.get("project", {}) if isinstance(data.get("project"), Mapping) else {}
        logging_data = data.get("logging", {}) if isinstance(data.get("logging"), Mapping) else {}

        project_name = str(project.get("name", "ISKCON NRJD Video Editor"))
        environment = str(project.get("environment", "production"))
        log_level = str(logging_data.get("level", "INFO"))
        log_directory = str(logging_data.get("log_directory", "output/logs"))

        return cls(
            config_path=config_path,
            project_name=project_name,
            environment=environment,
            log_level=log_level,
            log_directory=log_directory,
            data=data,
        )
