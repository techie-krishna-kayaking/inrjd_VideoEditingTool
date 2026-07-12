"""Unit tests for reusable image slideshow engine modules."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.image.image_animator import ANIMATIONS, AnimationOptions, ImageAnimator
from src.image.image_effects import ColorEffectOptions
from src.image.image_loader import ImageLoader
from src.image.image_processor import ImageProcessor, ProcessorOptions
from src.image.image_validator import ImageValidator, ValidationOptions
from src.image.slideshow import SlideshowEngine, SlideshowOptions
from src.image.timeline_builder import DurationOptions


def _write_image(path: Path, width: int, height: int, color: tuple[int, int, int] = (120, 120, 120)) -> None:
    """Create and save a test image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), color=color)
    image.save(path)


def test_validator_skips_corrupted_tiny_and_duplicate(tmp_path: Path) -> None:
    """Validator should keep only readable non-tiny non-duplicate images."""
    valid = tmp_path / "valid.jpg"
    tiny = tmp_path / "tiny.jpg"
    duplicate = tmp_path / "duplicate.jpg"
    corrupted = tmp_path / "broken.jpg"

    _write_image(valid, 1200, 900)
    _write_image(tiny, 200, 200)
    valid_bytes = valid.read_bytes()
    duplicate.write_bytes(valid_bytes)
    corrupted.write_text("not-an-image", encoding="utf-8")

    validator = ImageValidator()
    result = validator.validate(
        [valid, tiny, duplicate, corrupted],
        ValidationOptions(min_width=640, min_height=640, skip_duplicates=True),
    )

    assert result.valid_paths == [valid]
    reasons = {reason for _, reason in result.skipped}
    assert "tiny" in reasons
    assert "duplicate" in reasons
    assert "corrupted_or_unreadable" in reasons


def test_loader_order_modes(tmp_path: Path) -> None:
    """Loader should support original, chronological, and random ordering."""
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    third = tmp_path / "c.jpg"
    _write_image(first, 1000, 1000)
    _write_image(second, 1000, 1000)
    _write_image(third, 1000, 1000)

    loader = ImageLoader(random_seed=13)
    loaded = loader.load_paths([first, second, third])
    assert loaded == [first, second, third]

    original = loader.order_paths(loaded, "original")
    assert original == [first, second, third]

    chronological = loader.order_paths(loaded, "chronological")
    assert set(chronological) == {first, second, third}

    randomized = loader.order_paths(loaded, "random")
    assert set(randomized) == {first, second, third}


def test_animator_avoids_consecutive_repeat() -> None:
    """Animator should avoid selecting same animation consecutively."""
    animator = ImageAnimator(random_seed=11)
    options = AnimationOptions(enabled=True, random_per_image=True, allowed=ANIMATIONS)

    previous = None
    for _ in range(20):
        selected = animator.choose(options)
        current = str(selected["name"])
        if previous is not None:
            assert current != previous
        previous = current


def test_processor_reuses_cache(tmp_path: Path) -> None:
    """Processor should reuse cached output for unchanged source and settings."""
    source = tmp_path / "source.jpg"
    _write_image(source, 1800, 1200)

    processor = ImageProcessor(cache_dir=tmp_path / "cache")
    processor_options = ProcessorOptions(width=1280, height=720, fit_mode="center_crop", safe_area_ratio=0.9)
    color_options = ColorEffectOptions()

    first = processor.process(source, processor_options=processor_options, color_options=color_options)
    second = processor.process(source, processor_options=processor_options, color_options=color_options)

    assert first == second
    assert first.exists()


def test_slideshow_engine_builds_timeline_objects_only(tmp_path: Path) -> None:
    """Slideshow engine should produce timeline clips, not rendering commands."""
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    _write_image(image_a, 1800, 1200, color=(200, 150, 120))
    _write_image(image_b, 1200, 1800, color=(90, 130, 180))

    engine = SlideshowEngine(cache_dir=tmp_path / "cache", random_seed=7)
    result = engine.build(
        image_paths=[image_a, image_b],
        options=SlideshowOptions(
            target_duration=6.0,
            target_width=1280,
            target_height=720,
            transition_type="cross_dissolve",
            image_order="original",
            fit_mode="center_crop",
            safe_area_ratio=0.9,
        ),
        validation_options=ValidationOptions(min_width=640, min_height=640, skip_duplicates=True),
        duration_options=DurationOptions(image_duration=1.5, random_duration=False),
        animation_options=AnimationOptions(enabled=True, random_per_image=True),
        color_options=ColorEffectOptions(),
    )

    assert result.loaded_images == 2
    assert result.skipped_images == 0
    assert result.timeline.total_duration == 6.0
    assert len(result.timeline.clips) >= 3

    first_clip = result.timeline.clips[0]
    assert isinstance(first_clip.duration, float)
    assert "name" in first_clip.animation
    assert isinstance(first_clip.image_path, Path)
    assert "ffmpeg" not in str(first_clip)


def test_slideshow_engine_uses_discrete_duration_choices(tmp_path: Path) -> None:
    """Slideshow engine should draw random durations from provided discrete choices."""
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    _write_image(image_a, 1800, 1200, color=(210, 130, 100))
    _write_image(image_b, 1200, 1800, color=(100, 130, 210))

    engine = SlideshowEngine(cache_dir=tmp_path / "cache", random_seed=5)
    result = engine.build(
        image_paths=[image_a, image_b],
        options=SlideshowOptions(
            target_duration=5.0,
            target_width=1280,
            target_height=720,
            transition_type="cross_dissolve",
        ),
        validation_options=ValidationOptions(min_width=640, min_height=640, skip_duplicates=True),
        duration_options=DurationOptions(
            random_duration=True,
            minimum=0.5,
            maximum=1.5,
            duration_choices=(0.5, 1.0, 1.5),
        ),
        animation_options=AnimationOptions(enabled=True, random_per_image=True),
        color_options=ColorEffectOptions(),
    )

    allowed = {0.5, 1.0, 1.5}
    for clip in result.timeline.clips[:-1]:
        assert clip.duration in allowed
    assert all(0.1 <= clip.duration <= 1.5 for clip in result.timeline.clips)
