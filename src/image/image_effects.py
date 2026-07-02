"""Conservative cinematic color enhancement helpers."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter


@dataclass(slots=True)
class ColorEffectOptions:
    """Image enhancement controls."""

    brightness: float = 0.03
    contrast: float = 1.05
    saturation: float = 1.05
    gamma: float = 1.0
    sharpen: float = 0.2


class ImageEffects:
    """Apply mild visual polish while avoiding over-processing."""

    def apply(self, image: Image.Image, options: ColorEffectOptions) -> Image.Image:
        """Apply brightness, contrast, saturation, gamma, and sharpening."""
        result = image.convert("RGB")

        brightness_factor = _clamp(1.0 + options.brightness, 0.8, 1.2)
        contrast_factor = _clamp(options.contrast, 0.8, 1.2)
        saturation_factor = _clamp(options.saturation, 0.8, 1.2)
        gamma_value = _clamp(options.gamma, 0.8, 1.2)
        sharpen_strength = _clamp(options.sharpen, 0.0, 1.0)

        result = ImageEnhance.Brightness(result).enhance(brightness_factor)
        result = ImageEnhance.Contrast(result).enhance(contrast_factor)
        result = ImageEnhance.Color(result).enhance(saturation_factor)
        result = _apply_gamma(result, gamma_value)

        if sharpen_strength > 0:
            # Blend original and sharpened image to avoid harsh artifacts.
            sharpened = result.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
            result = Image.blend(result, sharpened, alpha=sharpen_strength * 0.5)

        return result


def _apply_gamma(image: Image.Image, gamma: float) -> Image.Image:
    """Apply gamma correction using LUT."""
    if abs(gamma - 1.0) < 1e-6:
        return image

    inverse = 1.0 / gamma
    lut = [
        int(_clamp((index / 255.0) ** inverse, 0.0, 1.0) * 255.0)
        for index in range(256)
    ]
    return image.point(lut * 3)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp floating point value to a closed interval."""
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
