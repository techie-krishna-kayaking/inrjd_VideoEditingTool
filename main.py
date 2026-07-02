"""Application entry point for ISKCON NRJD Video Editor."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from src.cli.app import create_cli
from src.config.config_manager import ConfigManager, ConfigManagerError
from src.logging.setup import initialize_logger


def main() -> None:
    """Initialize configuration, logger, and CLI application runtime."""
    project_root = Path(__file__).resolve().parent
    console = Console()

    try:
        settings = ConfigManager.load(project_root=project_root)
    except ConfigManagerError as exc:
        console.print(f"Configuration error: {exc}")
        raise SystemExit(2)

    log_directory = project_root / settings.paths.logs
    initialize_logger(
        log_directory=log_directory,
        log_level=settings.logging.level,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
        console_enabled=settings.logging.console,
        file_enabled=settings.logging.file,
    )

    app = create_cli(settings=settings)
    app()


if __name__ == "__main__":
    main()
