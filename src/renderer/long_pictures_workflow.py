"""Automated long-form picture rendering workflow for one cinematic output per event."""

from __future__ import annotations

import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml
from loguru import logger
from PIL import Image, ImageOps

from src.config.config_models import Settings
from src.image.image_animator import AnimationOptions
from src.image.image_effects import ColorEffectOptions
from src.image.image_validator import ValidationOptions
from src.image.slideshow import SlideshowEngine, SlideshowOptions
from src.image.timeline_builder import DurationOptions, Timeline


@dataclass(slots=True)
class LongRenderResult:
    """Per-event long render summary."""

    event_name: str
    output_file: Path
    thumbnail_path: Path
    report_path: Path


@dataclass(slots=True)
class _TransitionChoice:
    """Transition selection with ffmpeg xfade mapping."""

    label: str
    ffmpeg_name: str


class LongPicturesWorkflow:
    """Render one long-form landscape video from all longform_pictures images."""

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
            cache_dir=settings.project_root / settings.paths.temp / "slideshow_cache_long",
            random_seed=random_seed,
        )

    def render(self, event_name: str | None = None, profile: str | None = None) -> list[LongRenderResult]:
        """Render all eligible events or one requested event."""
        events = [event_name] if event_name else self._discover_events()
        results: list[LongRenderResult] = []
        profile_cfg = self._load_profile(profile)

        for current_event in events:
            if current_event is None:
                continue
            result = self._render_event(current_event, profile_cfg=profile_cfg)
            if result is not None:
                results.append(result)

        return results

    def _discover_events(self) -> list[str]:
        """Discover events from input directory."""
        input_root = self._settings.project_root / self._settings.paths.input
        if not input_root.exists() or not input_root.is_dir():
            return []
        return sorted(item.name for item in input_root.iterdir() if item.is_dir())

    def _render_event(self, event_name: str, profile_cfg: dict[str, Any]) -> LongRenderResult | None:
        """Render long-form picture video for one event."""
        logger.info("Loading Images | event={}", event_name)

        event_input = self._settings.project_root / self._settings.paths.input / event_name / "longform_pictures"
        if not event_input.exists() or not event_input.is_dir():
            logger.warning("Skipped event with missing longform_pictures folder | event={}", event_name)
            return None

        source_images = [path for path in event_input.iterdir() if path.is_file()]
        if not source_images:
            logger.warning("Skipped event with no long-form source images | event={}", event_name)
            return None

        output_dir = self._settings.project_root / self._settings.paths.output / "long" / event_name
        output_dir.mkdir(parents=True, exist_ok=True)

        order_mode = str(profile_cfg.get("image_order", "chronological_exif")).strip().lower()
        ordered_images = self._ordered_images(source_images, order_mode)

        min_duration = float(self._settings.long.duration.minimum)
        default_duration = float(self._settings.long.duration.default)
        max_duration = float(self._settings.long.duration.maximum)
        target_duration = _clamp(float(profile_cfg.get("target_duration", default_duration)), min_duration, max_duration)

        transition_selector = _TransitionSelector(
            random_source=self._rng,
            probabilities=self._load_transition_probabilities(profile_cfg),
            enabled=self._settings.transitions,
        )

        logger.info("Building Timeline | event={} order={} image_duration_mode=random_buckets", event_name, order_mode)

        fit_mode = str(profile_cfg.get("fit_mode", "center_crop"))
        timeline = self._build_timeline(
            images=ordered_images,
            transition_label="cross_dissolve",
            target_duration=target_duration,
            fit_mode=fit_mode,
        )

        if not timeline.clips:
            logger.warning("Skipped event with empty timeline after validation | event={}", event_name)
            return None

        transition_plan = transition_selector.choose_many(max(0, len(timeline.clips) - 1))

        output_name = f"{event_name}-long-pictures.mp4"
        output_path = output_dir / output_name

        music_plan = self._build_music_plan(total_duration=timeline.total_duration)

        logger.info("Adding Music | event={} tracks={}", event_name, len(music_plan))
        logger.info("Adding Overlays | event={}", event_name)
        logger.info("Rendering | event={}", event_name)

        started = time.perf_counter()
        self._render_timeline_video(
            timeline=timeline,
            transition_plan=transition_plan,
            output_path=output_path,
            event_name=event_name,
            music_plan=music_plan,
            profile_cfg=profile_cfg,
        )
        render_time = time.perf_counter() - started

        thumbnail_dir = self._settings.project_root / self._settings.paths.output / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_path = thumbnail_dir / f"{event_name}-thumbnail.jpg"
        self._write_thumbnail(timeline, thumbnail_path)

        report_payload = {
            "event_name": event_name,
            "images_used": [str(clip.image_path) for clip in timeline.clips],
            "image_order_mode": order_mode,
            "music_tracks_used": [str(item["path"]) for item in music_plan],
            "duration": round(timeline.total_duration, 3),
            "transitions": [choice.label for choice in transition_plan],
            "render_time": round(render_time, 3),
            "thumbnail_path": str(thumbnail_path),
            "output_file": str(output_path),
        }

        report_path = output_dir / "long_pictures_report.json"
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

        logger.info("Completed | event={} output={}", event_name, output_path)
        return LongRenderResult(
            event_name=event_name,
            output_file=output_path,
            thumbnail_path=thumbnail_path,
            report_path=report_path,
        )

    def _build_timeline(
        self,
        images: list[Path],
        transition_label: str,
        target_duration: float,
        fit_mode: str,
    ) -> Timeline:
        """Build image-only timeline using reusable slideshow engine."""
        return self._slideshow_engine.build(
            image_paths=images,
            options=SlideshowOptions(
                target_duration=target_duration,
                target_width=self._settings.long.resolution.width,
                target_height=self._settings.long.resolution.height,
                transition_type=transition_label,
                image_order="original",
                fit_mode=fit_mode,
                safe_area_ratio=0.9,
            ),
            validation_options=ValidationOptions(
                min_width=640,
                min_height=480,
                skip_duplicates=True,
            ),
            duration_options=DurationOptions(
                image_duration=1.0,
                random_duration=True,
                minimum=0.5,
                maximum=1.5,
                duration_choices=(0.5, 1.0, 1.5),
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
        transition_plan: list[_TransitionChoice],
        output_path: Path,
        event_name: str,
        music_plan: list[dict[str, Any]],
        profile_cfg: dict[str, Any],
    ) -> None:
        """Render timeline through ffmpeg using xfade transitions, overlays, and ending."""
        width = self._settings.long.resolution.width
        height = self._settings.long.resolution.height
        fps = self._settings.long.fps
        transition_duration = _clamp(self._settings.transitions.duration, 0.2, 1.2)
        total_duration = round(timeline.total_duration, 3)

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

        for plan in music_plan:
            command.extend(["-ss", str(round(float(plan["start"]), 3)), "-i", str(plan["path"])])

        filter_complex_video = self._build_filter_complex(
            clips=timeline,
            width=width,
            height=height,
            fps=fps,
            transition_plan=transition_plan,
            transition_duration=transition_duration,
            title_text=event_name,
            ending_text=str(profile_cfg.get("ending_text", "Hare Krishna")),
            total_duration=total_duration,
        )

        filter_complex = filter_complex_video

        if music_plan:
            music_base_index = len(timeline.clips)
            audio_chain = self._build_audio_chain(
                music_plan=music_plan,
                music_base_index=music_base_index,
                total_duration=total_duration,
            )
            filter_complex = f"{filter_complex_video};{audio_chain}"
            command.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"])
        else:
            command.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-an"])

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
        transition_plan: list[_TransitionChoice],
        transition_duration: float,
        title_text: str,
        ending_text: str,
        total_duration: float,
    ) -> str:
        """Build video filter graph for clips, transitions, overlays, opening and ending."""
        parts: list[str] = []
        clip_labels: list[str] = []

        for index, clip in enumerate(clips.clips):
            animation_name = str(clip.animation.get("name", "zoom_in"))
            zoom = float(clip.animation.get("zoom", 1.06))
            frame_count = max(1, int(round(clip.duration * fps)))
            zoom_expr, x_expr, y_expr = _zoompan_expressions(animation_name=animation_name, zoom=zoom)

            label = f"v{index}"
            chain = (
                f"[{index}:v]"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frame_count}:s={width}x{height}:fps={fps},"
                f"setsar=1,format=yuv420p[{label}]"
            )
            parts.append(chain)
            clip_labels.append(label)

        current = clip_labels[0]
        elapsed = clips.clips[0].duration

        for index in range(1, len(clip_labels)):
            nxt = clip_labels[index]
            out = f"x{index}"
            offset = max(0.0, elapsed - transition_duration)
            plan_transition = transition_plan[index - 1] if index - 1 < len(transition_plan) else _TransitionChoice(
                "cross_dissolve", "fade"
            )
            transition_name = plan_transition.ffmpeg_name if plan_transition.label != "hard_cut" else "fade"
            duration = transition_duration if plan_transition.label != "hard_cut" else 0.001
            parts.append(
                f"[{current}][{nxt}]xfade=transition={transition_name}:duration={duration}:offset={offset}[{out}]"
            )
            current = out
            elapsed += clips.clips[index].duration - duration

        parts.append(
            self._overlay_chain(
                video_label=current,
                width=width,
                height=height,
                title_text=title_text,
                ending_text=ending_text,
                total_duration=total_duration,
            )
        )
        return ";".join(parts)

    def _overlay_chain(
        self,
        video_label: str,
        width: int,
        height: int,
        title_text: str,
        ending_text: str,
        total_duration: float,
    ) -> str:
        """Build overlays, opening title, and ending text/fade chain."""
        overlays_root = self._settings.project_root / self._settings.paths.assets / "overlays"
        socials = overlays_root / "socials.png"
        website = overlays_root / "website.png"
        font_path = self._settings.project_root / self._settings.text_overlay.font

        parts: list[str] = []
        current = video_label

        if socials.exists():
            parts.append(f"movie={_ff_escape(str(socials))},scale=iw*0.35:-1[soc]")
            parts.append(f"[{current}][soc]overlay=20:20:format=auto[vs]")
            current = "vs"

        if website.exists():
            parts.append(f"movie={_ff_escape(str(website))},scale=iw*0.35:-1[web]")
            parts.append(f"[{current}][web]overlay=W-w-20:20:format=auto[vw]")
            current = "vw"

        ending_start = max(0.0, total_duration - 5.0)

        parts.append(
            f"[{current}]"
            f"drawtext=fontfile='{_ff_escape(str(font_path))}':text='{_ff_escape(title_text.upper())}':"
            f"fontsize=84:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
            f"shadowx=4:shadowy=4:shadowcolor=black@0.5:"
            f"alpha='if(lt(t,1),t/1,if(lt(t,4),1,if(lt(t,5),(5-t)/1,0)))',"
            f"drawtext=fontfile='{_ff_escape(str(font_path))}':text='{_ff_escape(ending_text)}':"
            f"fontsize=66:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
            f"shadowx=3:shadowy=3:shadowcolor=black@0.45:enable='gte(t,{ending_start})',"
            f"fade=t=out:st={ending_start}:d=5"
            f"[vout]"
        )

        return ";".join(parts)

    def _build_audio_chain(self, music_plan: list[dict[str, Any]], music_base_index: int, total_duration: float) -> str:
        """Build multi-track audio chain with crossfades and normalization."""
        crossfade = _clamp(self._settings.audio.crossfade, 0.1, 5.0)
        volume = _clamp(self._settings.audio.music_volume, 0.0, 1.0)
        fade_in = _clamp(self._settings.audio.fade_in, 0.0, 5.0)
        fade_out = _clamp(self._settings.audio.fade_out, 0.0, 5.0)

        parts: list[str] = []
        labels: list[str] = []

        for index, plan in enumerate(music_plan):
            source_index = music_base_index + index
            label = f"a{index}"
            duration = float(plan["use_seconds"])
            parts.append(
                f"[{source_index}:a]atrim=0:{duration},asetpts=PTS-STARTPTS[{label}]"
            )
            labels.append(label)

        if not labels:
            return "anullsrc=r=48000:cl=stereo[aout]"

        current = labels[0]
        for index in range(1, len(labels)):
            out = f"ax{index}"
            parts.append(f"[{current}][{labels[index]}]acrossfade=d={crossfade}:c1=tri:c2=tri[{out}]")
            current = out

        fade_out_start = max(0.0, total_duration - fade_out)
        parts.append(
            f"[{current}]"
            f"atrim=0:{total_duration},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={fade_out_start}:d={fade_out},"
            f"volume={volume},loudnorm[aout]"
        )

        return ";".join(parts)

    def _build_music_plan(self, total_duration: float) -> list[dict[str, Any]]:
        """Build random-track music plan that can cover full duration."""
        tracks = self._list_music_files()
        if not tracks:
            return []

        plan: list[dict[str, Any]] = []
        accumulated = 0.0
        target = total_duration + _clamp(self._settings.audio.crossfade, 0.1, 5.0)

        while accumulated < target:
            track = self._rng.choice(tracks)
            length = self._probe_audio_duration(track)
            if length <= 0.5:
                break
            start = self._rng.uniform(0.0, max(0.0, length * 0.5))
            available = max(0.5, length - start)
            use_seconds = min(available, target - accumulated + self._settings.audio.crossfade)
            plan.append({"path": track, "start": start, "use_seconds": use_seconds})
            accumulated += max(0.1, use_seconds - self._settings.audio.crossfade)

            if len(plan) > 20:
                break

        return plan

    def _list_music_files(self) -> list[Path]:
        """List usable music files from configured music directory."""
        music_dir = self._settings.project_root / self._settings.paths.music
        if not music_dir.exists() or not music_dir.is_dir():
            return []

        supported = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
        return sorted(item for item in music_dir.iterdir() if item.is_file() and item.suffix.lower() in supported)

    def _probe_audio_duration(self, audio_path: Path) -> float:
        """Probe audio duration using ffprobe with fallback estimate."""
        ffprobe = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        completed = self._run_command(ffprobe)
        if completed.returncode == 0:
            try:
                return float((completed.stdout or "").strip())
            except ValueError:
                pass

        size_mb = audio_path.stat().st_size / (1024 * 1024)
        return max(30.0, size_mb * 8.0)

    def _ordered_images(self, paths: list[Path], order_mode: str) -> list[Path]:
        """Order images by requested mode with EXIF-aware chronology."""
        mode = order_mode.strip().lower()
        if mode == "random":
            ordered = list(paths)
            self._rng.shuffle(ordered)
            return ordered
        if mode == "original":
            return sorted(paths)
        if mode in {"chronological", "chronological_exif"}:
            exif_pairs = [(path, _exif_timestamp(path)) for path in paths]
            if any(ts is not None for _, ts in exif_pairs):
                return [path for path, _ in sorted(exif_pairs, key=lambda item: item[1] or "9999:99:99 99:99:99")]
            return sorted(paths)
        return sorted(paths)

    def _write_thumbnail(self, timeline: Timeline, thumbnail_path: Path) -> None:
        """Write representative thumbnail from middle timeline image."""
        if not timeline.clips:
            return
        middle_index = len(timeline.clips) // 2
        source = timeline.clips[middle_index].image_path
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (1280, 720), (0, 0, 0))
            offset_x = (1280 - image.width) // 2
            offset_y = (720 - image.height) // 2
            canvas.paste(image, (offset_x, offset_y))
            canvas.save(thumbnail_path, format="JPEG", quality=92)

    def _load_profile(self, profile: str | None) -> dict[str, Any]:
        """Load optional profile overrides from YAML.

        Defaults are used when profile sections are absent.
        """
        defaults: dict[str, Any] = {
            "target_duration": float(self._settings.long.duration.default),
            "image_order": "chronological_exif",
            "fit_mode": "center_crop",
            "image_duration_min": 1.2,
            "image_duration_max": 8.0,
            "ending_text": "Hare Krishna",
        }

        try:
            payload = yaml.safe_load(self._settings.config_path.read_text(encoding="utf-8"))
        except Exception:
            return defaults

        if not isinstance(payload, dict):
            return defaults

        section = payload.get("long_picture_render")
        if isinstance(section, dict):
            defaults.update({k: v for k, v in section.items() if not isinstance(v, dict)})
            profiles = section.get("profiles")
            if profile and isinstance(profiles, dict) and isinstance(profiles.get(profile), dict):
                defaults.update(profiles[profile])

        return defaults

    def _load_transition_probabilities(self, profile_cfg: dict[str, Any]) -> dict[str, float]:
        """Load transition probabilities from profile or safe defaults."""
        defaults = {
            "hard_cut": 0.15,
            "cross_dissolve": 0.45,
            "film_burn": 0.1,
            "fade_through_black": 0.3,
        }

        custom = profile_cfg.get("transition_probabilities")
        if not isinstance(custom, dict):
            return defaults

        merged: dict[str, float] = {}
        for key, fallback in defaults.items():
            try:
                merged[key] = max(0.0, float(custom.get(key, fallback)))
            except (TypeError, ValueError):
                merged[key] = fallback

        if sum(merged.values()) <= 0:
            return defaults
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
            available = ["cross_dissolve"]

        candidates = [name for name in available if name != self._last]
        if not candidates:
            candidates = available

        weights = [self._probabilities.get(name, 1.0) for name in candidates]
        chosen = self._rng.choices(candidates, weights=weights, k=1)[0]
        self._last = chosen
        return self._mapping[chosen]

    def choose_many(self, count: int) -> list[_TransitionChoice]:
        """Pick a transition sequence for consecutive clip boundaries."""
        if count <= 0:
            return []
        return [self.choose() for _ in range(count)]


def _zoompan_expressions(animation_name: str, zoom: float) -> tuple[str, str, str]:
    """Return zoompan expressions for supported animation names."""
    base_zoom = max(1.01, min(1.2, zoom))
    if animation_name == "zoom_out":
        return (
            f"if(eq(on,1),{base_zoom},max(1.0,zoom-0.0007))",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if animation_name == "pan_left":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.00045))",
            "(iw-iw/zoom)*(1-on/500)",
            "ih/2-(ih/zoom/2)",
        )
    if animation_name == "pan_right":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.00045))",
            "(iw-iw/zoom)*(on/500)",
            "ih/2-(ih/zoom/2)",
        )
    if animation_name == "pan_up":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.00045))",
            "iw/2-(iw/zoom/2)",
            "(ih-ih/zoom)*(1-on/500)",
        )
    if animation_name == "pan_down":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.00045))",
            "iw/2-(iw/zoom/2)",
            "(ih-ih/zoom)*(on/500)",
        )
    if animation_name == "diagonal":
        return (
            f"if(eq(on,1),1.0,min({base_zoom},zoom+0.00045))",
            "(iw-iw/zoom)*(on/500)",
            "(ih-ih/zoom)*(on/500)",
        )

    return (
        f"if(eq(on,1),1.0,min({base_zoom},zoom+0.0006))",
        "iw/2-(iw/zoom/2)",
        "ih/2-(ih/zoom/2)",
    )


def _exif_timestamp(path: Path) -> str | None:
    """Read EXIF DateTimeOriginal timestamp when available."""
    try:
        with Image.open(path) as opened:
            exif = opened.getexif()
            value = exif.get(36867) or exif.get(306)
            if isinstance(value, str) and value.strip():
                return value.strip()
    except Exception:
        return None
    return None


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
