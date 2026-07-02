"""Central configuration manager for one-time loading and caching."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from src.config.config_loader import (
    apply_environment_overrides,
    build_settings,
    load_yaml_file,
    merge_with_defaults,
    validate_required_sections,
)
from src.config.config_models import Settings
from src.config.config_validator import validate_settings


class ConfigManagerError(Exception):
    """Raised when config manager cannot provide a valid settings object."""


class ConfigManager:
    """Singleton-style configuration manager for centralized access."""

    _settings: Settings | None = None

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        project_root: Path | None = None,
        force_reload: bool = False,
    ) -> Settings:
        """Load, validate, and cache configuration settings."""
        if cls._settings is not None and not force_reload:
            return cls._settings

        resolved_root = (
            project_root.resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        resolved_config = (
            config_path.resolve()
            if config_path is not None
            else (resolved_root / "config" / "config.yaml").resolve()
        )

        try:
            raw_data = load_yaml_file(resolved_config)
            validate_required_sections(raw_data)
            merged_data = merge_with_defaults(raw_data)

            env_cfg = merged_data.get("environment", {})
            dotenv_enabled = bool(env_cfg.get("dotenv_enabled", True))
            if dotenv_enabled:
                load_dotenv(dotenv_path=resolved_root / ".env", override=False)

            apply_environment_overrides(merged_data)
            settings = build_settings(
                config_path=resolved_config,
                project_root=resolved_root,
                data=merged_data,
            )
            validate_settings(settings)
        except Exception as exc:  # noqa: BLE001
            raise ConfigManagerError(str(exc)) from None

        cls._settings = settings
        return settings

    @classmethod
    def get(cls) -> Settings:
        """Return loaded settings or load with default paths."""
        if cls._settings is None:
            return cls.load()
        return cls._settings

    @classmethod
    def reset(cls) -> None:
        """Reset cached settings for tests and controlled reloads."""
        cls._settings = None
