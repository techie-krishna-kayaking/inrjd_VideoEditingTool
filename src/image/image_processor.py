"""Image preprocessing for slideshow-ready still frames."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from src.image.image_effects import ColorEffectOptions, ImageEffects


@dataclass(slots=True)
class ProcessorOptions:
    """Preprocessing options for resized and enhanced output images."""

    width: int
    height: int
    fit_mode: str = "center_crop"
    safe_area_ratio: float = 0.9
    cache_enabled: bool = True


class ImageProcessor:
    """Process input images into cacheable slideshow frame assets."""

    def __init__(self, cache_dir: Path, effects: ImageEffects | None = None) -> None:
        """Initialize processor with cache directory and effects applier."""
        self._cache_dir = cache_dir
        self._effects = effects if effects is not None else ImageEffects()

    def process(
        self,
        source_path: Path,
        processor_options: ProcessorOptions,
        color_options: ColorEffectOptions,
    ) -> Path:
        """Process one image and return cached processed path."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self._cache_path(source_path=source_path, options=processor_options, color=color_options)

        if processor_options.cache_enabled and cache_path.exists():
            return cache_path

        with Image.open(source_path) as opened:
            corrected = ImageOps.exif_transpose(opened).convert("RGB")
            fitted = _fit_image(
                image=corrected,
                width=processor_options.width,
                height=processor_options.height,
                fit_mode=processor_options.fit_mode,
                safe_area_ratio=processor_options.safe_area_ratio,
            )
            enhanced = self._effects.apply(fitted, color_options)
            enhanced.save(cache_path, format="JPEG", quality=95)

        return cache_path

    def _cache_path(self, source_path: Path, options: ProcessorOptions, color: ColorEffectOptions) -> Path:
        """Derive deterministic cache file path from source and options."""
        stat = source_path.stat()
        signature = (
            f"{source_path.resolve()}|{int(stat.st_mtime)}|{stat.st_size}|"
            f"{options.width}x{options.height}|{options.fit_mode}|{options.safe_area_ratio}|"
            f"{color.brightness}|{color.contrast}|{color.saturation}|{color.gamma}|{color.sharpen}"
        )
        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.jpg"


def _fit_image(image: Image.Image, width: int, height: int, fit_mode: str, safe_area_ratio: float) -> Image.Image:
    """Fit image into target frame without distortion."""
    mode = fit_mode.strip().lower()
    if mode == "contain":
        return _fit_contain(image=image, width=width, height=height)
    if mode == "blur_background":
        return _fit_blur_background(image=image, width=width, height=height)
    if mode == "center_crop":
        return _fit_center_crop(image=image, width=width, height=height, safe_area_ratio=safe_area_ratio)
    raise ValueError(f"Unsupported fit mode: {fit_mode}")


def _fit_center_crop(image: Image.Image, width: int, height: int, safe_area_ratio: float) -> Image.Image:
    """Center crop with conservative safe-area fallback."""
    src_w, src_h = image.size
    target_ratio = width / height
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = int(round(crop_h * target_ratio))
    else:
        crop_w = src_w
        crop_h = int(round(crop_w / target_ratio))

    min_crop_w = int(round(src_w * safe_area_ratio))
    min_crop_h = int(round(src_h * safe_area_ratio))
    if crop_w < min_crop_w or crop_h < min_crop_h:
        # Safe-area protection falls back to contain when crop would be too aggressive.
        return _fit_contain(image=image, width=width, height=height)

    left = max(0, (src_w - crop_w) // 2)
    top = max(0, (src_h - crop_h) // 2)
    cropped = image.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((width, height), resample=Image.Resampling.LANCZOS)


def _fit_contain(image: Image.Image, width: int, height: int) -> Image.Image:
    """Contain fit with black bars when aspect ratio differs."""
    contained = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), color=(0, 0, 0))
    offset_x = (width - contained.width) // 2
    offset_y = (height - contained.height) // 2
    canvas.paste(contained, (offset_x, offset_y))
    return canvas


def _fit_blur_background(image: Image.Image, width: int, height: int) -> Image.Image:
    """Contain foreground over blurred background fill."""
    background = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=18))

    foreground = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
    offset_x = (width - foreground.width) // 2
    offset_y = (height - foreground.height) // 2
    background.paste(foreground, (offset_x, offset_y))
    return background
