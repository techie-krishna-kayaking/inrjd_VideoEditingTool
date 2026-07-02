"""Reusable color grading preset resolver for render workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.config_models import ColorGradingSettings, Settings


@dataclass(slots=True)
class ColorPresetValues:
    """Resolved grading values used by ffmpeg filters."""

    brightness: float
    contrast: float
    saturation: float
    sharpen: float
    gamma: float


DEFAULT_PRESETS: dict[str, dict[str, float]] = {
    "natural": {"brightness": 0.0, "contrast": 1.02, "saturation": 1.02, "sharpen": 0.18, "gamma": 1.0},
    "temple": {"brightness": 0.02, "contrast": 1.06, "saturation": 1.08, "sharpen": 0.2, "gamma": 1.0},
    "festival": {"brightness": 0.03, "contrast": 1.1, "saturation": 1.14, "sharpen": 0.24, "gamma": 0.99},
    "cinematic": {"brightness": -0.01, "contrast": 1.08, "saturation": 0.95, "sharpen": 0.16, "gamma": 1.02},
    "warm": {"brightness": 0.01, "contrast": 1.04, "saturation": 1.09, "sharpen": 0.18, "gamma": 0.99},
    "cool": {"brightness": -0.005, "contrast": 1.05, "saturation": 0.96, "sharpen": 0.18, "gamma": 1.01},
}


def resolve_color_preset(settings: Settings, raw_config: dict[str, Any], preset_name: str | None = None) -> ColorPresetValues:
    """Resolve a named preset from YAML, falling back to config defaults."""
    base = _from_settings(settings.color_grading)
    selected = (preset_name or "").strip().lower()

    render_cfg = raw_config.get("video_render")
    custom_presets: dict[str, dict[str, float]] = {}
    default_name = "natural"

    if isinstance(render_cfg, dict):
        default_name = str(render_cfg.get("color_preset", "natural")).strip().lower() or "natural"
        configured = render_cfg.get("color_presets")
        if isinstance(configured, dict):
            for key, values in configured.items():
                if not isinstance(values, dict):
                    continue
                custom_presets[str(key).strip().lower()] = {
                    "brightness": _safe_float(values.get("brightness"), base.brightness),
                    "contrast": _safe_float(values.get("contrast"), base.contrast),
                    "saturation": _safe_float(values.get("saturation"), base.saturation),
                    "sharpen": _safe_float(values.get("sharpen"), base.sharpen),
                    "gamma": _safe_float(values.get("gamma"), base.gamma),
                }

    final_name = selected or default_name

    if final_name in custom_presets:
        return _from_mapping(custom_presets[final_name])
    if final_name in DEFAULT_PRESETS:
        return _from_mapping(DEFAULT_PRESETS[final_name])
    return base


def _from_settings(settings: ColorGradingSettings) -> ColorPresetValues:
    """Build preset values from typed color grading settings."""
    return ColorPresetValues(
        brightness=float(settings.brightness),
        contrast=float(settings.contrast),
        saturation=float(settings.saturation),
        sharpen=float(settings.sharpen),
        gamma=float(settings.gamma),
    )


def _from_mapping(values: dict[str, float]) -> ColorPresetValues:
    """Build preset values from a generic mapping."""
    return ColorPresetValues(
        brightness=float(values["brightness"]),
        contrast=float(values["contrast"]),
        saturation=float(values["saturation"]),
        sharpen=float(values["sharpen"]),
        gamma=float(values["gamma"]),
    )


def _safe_float(value: Any, fallback: float) -> float:
    """Convert arbitrary values to float with fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
