"""Automated short-form picture rendering workflow."""

from __future__ import annotations

import json
import math
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml
from loguru import logger

from src.config.config_models import Settings
from src.image.image_animator import AnimationOptions
from src.image.image_effects import ColorEffectOptions
from src.image.image_validator import ValidationOptions
from src.image.slideshow import SlideshowEngine, SlideshowOptions
from src.image.timeline_builder import DurationOptions, Timeline


@dataclass(slots=True)
class RenderResult:
    """Per-event short render summary."""

    event_name: str
    rendered_files: list[Path]
    report_path: Path


@dataclass(slots=True)
class _TransitionChoice:
    """Transition selection with ffmpeg xfade mapping."""

    label: str
    ffmpeg_name: str


class ShortsPicturesWorkflow:
    """Render short-form picture-only videos for one or more events."""

    def __init__(
        self,
        settings: Settings,
        command_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        random_seed: int | None = None,
    ) -> None:
        """Initialize workflow with config and pluggable command execution."""
        self._settings = settings
        self._rng = random.Random(random_seed)
        self._run_command = command_runner if command_runner is not None else self._default_run_command
        self._slideshow_engine = SlideshowEngine(
            cache_dir=settings.project_root / settings.paths.temp / "slideshow_cache",
            random_seed=random_seed,
        )

    def render(self, event_name: str | None = None) -> list[RenderResult]:
        """Render all eligible events or one requested event."""
        events = [event_name] if event_name else self._discover_events()
        results: list[RenderResult] = []

        for current_event in events:
            if current_event is None:
                continue
            result = self._render_event(current_event)
            if result is not None:
                results.append(result)

        return results

    def _discover_events(self) -> list[str]:
        """Discover events from input directory."""
        input_root = self._settings.project_root / self._settings.paths.input
        if not input_root.exists() or not input_root.is_dir():
            return []
        return sorted(item.name for item in input_root.iterdir() if item.is_dir())

    def _render_event(self, event_name: str) -> RenderResult | None:
        """Render all short-form picture parts for one event."""
        logger.info("Loading Images | event={}", event_name)

        event_input = self._settings.project_root / self._settings.paths.input / event_name / "shortform_pictures"
        if not event_input.exists() or not event_input.is_dir():
            logger.warning("Skipped event with missing shortform_pictures folder | event={}", event_name)
            return None

        image_paths = sorted(path for path in event_input.iterdir() if path.is_file())
        if not image_paths:
            logger.warning("Skipped event with no source images | event={}", event_name)
            return None

        output_dir = self._settings.project_root / self._settings.paths.output / "shorts" / event_name
        output_dir.mkdir(parents=True, exist_ok=True)

        default_duration = float(self._settings.shorts.duration.default)
        min_duration = float(self._settings.shorts.duration.minimum)
        max_duration = float(self._settings.shorts.duration.maximum)
        image_duration = float(self._settings.images.image_duration)

        target_duration = _clamp(default_duration, min_duration, max_duration)
        images_per_part = max(1, int(target_duration / max(0.1, image_duration)))

        ordered = list(image_paths)
        self._rng.shuffle(ordered)

        parts: list[list[Path]] = []
        for start in range(0, len(ordered), images_per_part):
            chunk = ordered[start : start + images_per_part]
            if chunk:
                parts.append(chunk)

        if not parts:
            return None

        logger.info("Building Timeline | event={} parts={} images_per_part={}", event_name, len(parts), images_per_part)

        transitions = _TransitionSelector(
            random_source=self._rng,
            probabilities=self._load_transition_probabilities(),
            enabled=self._settings.transitions,
        )

        music_files = self._list_music_files()
        if not music_files:
            logger.warning("No background music files found. Videos will render without music.")

        rendered_files: list[Path] = []
        report_payload: dict[str, object] = {
            "event_name": event_name,
            "parts": [],
        }

        started_event = time.perf_counter()

        for index, chunk in enumerate(parts, start=1):
            part_label = f"part{index:02d}"
            output_name = f"{event_name}-short-picture-{part_label}.mp4"
            output_path = output_dir / output_name

            part_started = time.perf_counter()
            transition = transitions.choose()

            timeline = self._build_timeline(
                images=chunk,
                transition_label=transition.label,
                target_duration=target_duration,
            )

            if not timeline.clips:
                logger.warning("Skipped empty timeline | event={} part={}", event_name, part_label)
                continue

            music_used = self._rng.choice(music_files) if music_files else None

            logger.info("Adding Music | event={} part={} music={}", event_name, part_label, music_used)
            logger.info("Adding Overlays | event={} part={}", event_name, part_label)
            logger.info("Rendering | event={} part={}", event_name, part_label)

            self._render_timeline_video(
                timeline=timeline,
                transition=transition,
                output_path=output_path,
                music_path=music_used,
                title_text=event_name.upper(),
            )

            rendered_files.append(output_path)
            part_elapsed = time.perf_counter() - part_started

            part_payload = {
                "part": part_label,
                "output_file": str(output_path),
                "images_used": [str(item.image_path) for item in timeline.clips],
                "music_used": str(music_used) if music_used else None,
                "transitions_used": [transition.label],
                "render_time_seconds": round(part_elapsed, 3),
            }
            cast_list = report_payload.get("parts")
            if isinstance(cast_list, list):
                cast_list.append(part_payload)

        report_payload["event_render_time_seconds"] = round(time.perf_counter() - started_event, 3)

        report_path = output_dir / "shorts_picture_report.json"
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

        logger.info("Completed | event={} rendered_files={}", event_name, len(rendered_files))
        return RenderResult(event_name=event_name, rendered_files=rendered_files, report_path=report_path)

    def _build_timeline(self, images: list[Path], transition_label: str, target_duration: float) -> Timeline:
        """Build image-only timeline using reusable slideshow engine."""
        return self._slideshow_engine.build(
            image_paths=images,
            options=SlideshowOptions(
                target_duration=target_duration,
                target_width=self._settings.shorts.resolution.width,
                target_height=self._settings.shorts.resolution.height,
                transition_type=transition_label,
                image_order="original",
                fit_mode="center_crop",
                safe_area_ratio=0.88,
            ),
            validation_options=ValidationOptions(
                min_width=640,
                min_height=640,
                skip_duplicates=True,
            ),
            duration_options=DurationOptions(
                image_duration=self._settings.images.image_duration,
                random_duration=False,
                minimum=1.2,
                maximum=2.2,
            ),
            animation_options=AnimationOptions(
                enabled=True,
                random_per_image=True,
                random_mode=True,
                default_animation="zoom_in",
            ),
            color_options=ColorEffectOptions(
                brightness=self._settings.color_grading.brightness,
                contrast=self._settings.color_grading.contrast,
                saturation=self._settings.color_grading.saturation,
                gamma=self._settings.color_grading.gamma,
                sharpen=self._settings.color_grading.sharpen,
            ),
        ).timeline

    def _render_timeline_video(
        self,
        timeline: Timeline,
        transition: _TransitionChoice,
        output_path: Path,
        music_path: Path | None,
        title_text: str,
    ) -> None:
        """Render timeline through ffmpeg using xfade transitions and overlays."""
        temp_dir = self._settings.project_root / self._settings.paths.temp / "shorts_picture_work"
        temp_dir.mkdir(parents=True, exist_ok=True)

        width = self._settings.shorts.resolution.width
        height = self._settings.shorts.resolution.height
        fps = self._settings.shorts.fps
        transition_duration = _clamp(self._settings.transitions.duration, 0.2, 1.0)

        command: list[str] = [self._settings.render.ffmpeg_path, "-y"]

        for clip in timeline.clips:
            clip_duration = round(clip.duration + transition_duration, 4)
            command.extend([
                "-loop",
                "1",
                "-t",
                str(clip_duration),
                "-i",
                str(clip.image_path),
            ])

        music_index: int | None = None
        random_music_start = 0.0
        if music_path is not None:
            music_index = len(timeline.clips)
            random_music_start = self._pick_music_start(music_path)
            command.extend([
                "-stream_loop",
                "-1",
                "-ss",
                str(round(random_music_start, 3)),
                "-i",
                str(music_path),
            ])

        filter_complex_video = self._build_filter_complex(
            clips=timeline,
            width=width,
            height=height,
            fps=fps,
            transition=transition,
            transition_duration=transition_duration,
            title_text=title_text,
        )

        total_duration = round(timeline.total_duration, 3)

        filter_complex = filter_complex_video
        if music_index is not None:
            fade_in = _clamp(self._settings.audio.fade_in, 0.0, 5.0)
            fade_out = _clamp(self._settings.audio.fade_out, 0.0, 5.0)
            volume = _clamp(self._settings.audio.music_volume, 0.0, 1.0)
            fade_out_start = max(0.0, total_duration - fade_out)

            audio_filter = (
                f"[{music_index}:a]atrim=0:{total_duration},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out},"
                f"volume={volume},loudnorm[aout]"
            )
            filter_complex = f"{filter_complex_video};{audio_filter}"
            command.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"])
        else:
            command.extend(["-filter_complex", filter_complex])
            command.extend(["-an"])
            command.extend(["-map", "[vout]"])

        command.extend(
            [
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        completed = self._run_command(command)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg render failed for {output_path}: {completed.stderr}")

    def _build_filter_complex(
        self,
        clips: Timeline,
        width: int,
        height: int,
        fps: int,
        transition: _TransitionChoice,
        transition_duration: float,
        title_text: str,
    ) -> str:
        """Build video filter graph for image clips, transitions, overlays, and title."""
        parts: list[str] = []
        clip_labels: list[str] = []

        for index, clip in enumerate(clips.clips):
            animation_name = str(clip.animation.get("name", "zoom_in"))
            zoom = float(clip.animation.get("zoom", 1.06))
            frame_count = max(1, int(round(clip.duration * fps)))
            zoom_expr, x_expr, y_expr = _zoompan_expressions(animation_name=animation_name, zoom=zoom)

            label = f"v{index}"
            filter_chain = (
                f"[{index}:v]"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frame_count}:s={width}x{height}:fps={fps},"
                f"setsar=1,format=yuv420p[{label}]"
            )
            parts.append(filter_chain)
            clip_labels.append(label)

        current_label = clip_labels[0]
        elapsed = clips.clips[0].duration

        for index in range(1, len(clip_labels)):
            next_label = clip_labels[index]
            out_label = f"x{index}"
            offset = max(0.0, elapsed - transition_duration)
            transition_name = transition.ffmpeg_name if transition.label != "hard_cut" else "fade"
            duration = transition_duration if transition.label != "hard_cut" else 0.001

            parts.append(
                f"[{current_label}][{next_label}]xfade=transition={transition_name}:duration={duration}:offset={offset}[{out_label}]"
            )
            current_label = out_label
            elapsed += clips.clips[index].duration - duration

        overlay_chain = self._overlay_and_title_chain(
            video_label=current_label,
            width=width,
            height=height,
            title_text=title_text,
            fps=fps,
        )
        parts.append(overlay_chain)

        return ";".join(parts)

    def _overlay_and_title_chain(self, video_label: str, width: int, height: int, title_text: str, fps: int) -> str:
        """Build overlay and opening-title chain with fade and shadow."""
        assets_root = self._settings.project_root / self._settings.paths.assets / "overlays"
        header_path = assets_root / "shorts_header.png"
        footer_path = assets_root / "shorts_footer.png"
        font_path = self._settings.project_root / self._settings.text_overlay.font

        filters: list[str] = []
        current = video_label

        if header_path.exists():
            filters.append(
                f"movie={_ff_escape(str(header_path))},scale={width}:-1[hdr]"
            )
            filters.append(f"[{current}][hdr]overlay=(W-w)/2:0:format=auto[vh]")
            current = "vh"

        if footer_path.exists():
            filters.append(
                f"movie={_ff_escape(str(footer_path))},scale={width}:-1[ftr]"
            )
            filters.append(f"[{current}][ftr]overlay=(W-w)/2:H-h:format=auto[vf]")
            current = "vf"

        draw_chain = (
            f"[{current}]"
            f"drawbox=x=(w*0.12):y=(h*0.36):w=(w*0.76):h=(h*0.18):color=white@0.16:t=fill:enable='between(t,0,3)',"
            f"drawtext=fontfile='{_ff_escape(str(font_path))}':"
            f"text='{_ff_escape(title_text)}':"
            f"fontsize=96:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            f"shadowx=4:shadowy=4:shadowcolor=black@0.45:"
            f"alpha='if(lt(t,0.6),t/0.6,if(lt(t,2.4),1,if(lt(t,3),(3-t)/0.6,0)))'"
            f"[vout]"
        )
        filters.append(draw_chain)

        return ";".join(filters)

    def _list_music_files(self) -> list[Path]:
        """List usable music files from configured music directory."""
        music_dir = self._settings.project_root / self._settings.paths.music
        if not music_dir.exists() or not music_dir.is_dir():
            return []

        supported = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
        return sorted(item for item in music_dir.iterdir() if item.is_file() and item.suffix.lower() in supported)

    def _pick_music_start(self, music_path: Path) -> float:
        """Pick random offset to vary music intro alignment."""
        # Lightweight heuristic without ffprobe dependency; small random offset avoids repetitive intros.
        size_mb = music_path.stat().st_size / (1024 * 1024)
        estimated_seconds = max(10.0, size_mb * 8.0)
        return self._rng.uniform(0.0, max(0.0, estimated_seconds * 0.5))

    def _load_transition_probabilities(self) -> dict[str, float]:
        """Load optional transition probabilities from YAML, with safe defaults."""
        default_weights = {
            "hard_cut": 0.2,
            "cross_dissolve": 0.3,
            "film_burn": 0.2,
            "fade_through_black": 0.3,
        }
        config_path = self._settings.config_path
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            return default_weights

        if not isinstance(payload, dict):
            return default_weights

        custom = payload.get("shorts_picture_render", {}).get("transition_probabilities")
        if not isinstance(custom, dict):
            return default_weights

        merged: dict[str, float] = {}
        for key, default_value in default_weights.items():
            raw = custom.get(key, default_value)
            try:
                merged[key] = max(0.0, float(raw))
            except (TypeError, ValueError):
                merged[key] = default_value

        if sum(merged.values()) <= 0:
            return default_weights
        return merged

    def _default_run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """Run shell command and capture text output."""
        return subprocess.run(command, capture_output=True, text=True, check=False)


class _TransitionSelector:
    """Transition picker honoring configured probabilities and no-repeat rule."""

    _mapping = {
        "hard_cut": _TransitionChoice("hard_cut", "fade"),
        "cross_dissolve": _TransitionChoice("cross_dissolve", "fade"),
        "film_burn": _TransitionChoice("film_burn", "fadefast"),
        "fade_through_black": _TransitionChoice("fade_through_black", "fadeblack"),
    }

    def __init__(self, random_source: random.Random, probabilities: dict[str, float], enabled) -> None:
        """Initialize selector with random source and enabled transition toggles."""
        self._rng = random_source
        self._probabilities = probabilities
        self._last: str | None = None
        self._enabled_flags = {
            "hard_cut": bool(getattr(enabled, "hard_cut", True)),
            "cross_dissolve": bool(getattr(enabled, "cross_dissolve", True)),
            "film_burn": bool(getattr(enabled, "film_burn", True)),
            "fade_through_black": True,
        }

    def choose(self) -> _TransitionChoice:
        """Pick transition avoiding direct repetition where possible."""
        available = [name for name in self._mapping if self._enabled_flags.get(name, True)]
        if not available:
            available = ["hard_cut"]

        candidates = [name for name in available if name != self._last]
        if not candidates:
            candidates = available

        weights = [self._probabilities.get(name, 1.0) for name in candidates]
        chosen = self._rng.choices(candidates, weights=weights, k=1)[0]
        self._last = chosen
        return self._mapping[chosen]


def _zoompan_expressions(animation_name: str, zoom: float) -> tuple[str, str, str]:
    """Return zoompan expressions for supported animation names."""
    base_zoom = max(1.01, min(1.2, zoom))
    if animation_name == "zoom_out":
        return (
            f"if(eq(on,1),{base_zoom},max(1.0,zoom-0.0008))",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if animation_name == "pan_left":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0005))",
            "(iw-iw/zoom)*(1-on/300)",
            "ih/2-(ih/zoom/2)",
        )
    if animation_name == "pan_right":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0005))",
            "(iw-iw/zoom)*(on/300)",
            "ih/2-(ih/zoom/2)",
        )
    if animation_name == "pan_up":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0005))",
            "iw/2-(iw/zoom/2)",
            "(ih-ih/zoom)*(1-on/300)",
        )
    if animation_name == "pan_down":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0005))",
            "iw/2-(iw/zoom/2)",
            "(ih-ih/zoom)*(on/300)",
        )
    if animation_name == "diagonal":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0005))",
            "(iw-iw/zoom)*(on/300)",
            "(ih-ih/zoom)*(on/300)",
        )

    return (
        f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0007))",
        "iw/2-(iw/zoom/2)",
        "ih/2-(ih/zoom/2)",
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp float value to closed interval."""
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _ff_escape(value: str) -> str:
    """Escape text/path for ffmpeg filter expressions."""
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
