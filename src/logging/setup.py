"""Centralized Loguru logger initialization utilities."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def initialize_logger(
    log_directory: Path,
    log_level: str,
    rotation: str = "1 day",
    retention: str = "14 days",
    console_enabled: bool = True,
    file_enabled: bool = True,
) -> Path:
    """Configure console and file log sinks with daily rotation."""
    log_directory.mkdir(parents=True, exist_ok=True)
    log_file = log_directory / "application.log"

    logger.remove()

    if console_enabled:
        logger.add(
            sink=lambda message: print(message, end=""),
            level=log_level.upper(),
            colorize=False,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | "
                "{level: <8} | {module}:{function}:{line} | {message}"
                " | elapsed={elapsed}"
            ),
        )

    if file_enabled:
        logger.add(
            sink=str(log_file),
            level=log_level.upper(),
            rotation=rotation,
            retention=retention,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | "
                "{level: <8} | {module}:{function}:{line} | {message}"
                " | elapsed={elapsed}"
            ),
            enqueue=True,
        )

    return log_file
