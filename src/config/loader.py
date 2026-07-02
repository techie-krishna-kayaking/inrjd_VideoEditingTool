"""Backward-compatible loader wrapper for legacy imports."""

from __future__ import annotations

from pathlib import Path

from src.config.config_manager import ConfigManager, ConfigManagerError
from src.config.config_models import Settings


class ConfigurationError(Exception):
    """Raised when configuration cannot be loaded safely."""


def load_configuration(config_path: Path) -> Settings:
    """Load settings via the centralized configuration manager."""
    try:
        return ConfigManager.load(config_path=config_path, force_reload=True)
    except ConfigManagerError as exc:
        raise ConfigurationError(str(exc)) from None
