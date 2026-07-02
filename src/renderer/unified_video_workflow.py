"""Unified video processing engine for short-form and long-form clip rendering."""

from __future__ import annotations

import json
import random
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from loguru import logger

from src.config.config_models import Settings
from src.effects.color_presets import ColorPresetValues, resolve_color_preset
from src.reports.render_reporting import append_render_history, update_media_usage, write_report_artifacts


@dataclass(slots=True)
class VideoMetadata:
    """Source video metadata collected via ffprobe."""

    path: Path
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    rotation: int
    has_audio: bool
    bitrate: int
    orientation: str


@dataclass(slots=True)
class ClipSegment:
    """Single extracted clip segment from a source video."""

    source_path: Path
    start: float
    duration: float
    segment_id: str
    has_audio: bool


@dataclass(slots=True)
class TransitionChoice:
    """Transition choice with ffmpeg transition name and duration."""

    label: str
    ffmpeg_name: str
    duration: float


@dataclass(slots=True)
class TimelinePlan:
    """Resolved render timeline for one output video."""

    event_name: str
    mode: str
    output_index: int
    clips: list[ClipSegment]
    transitions: list[TransitionChoice]
    total_duration: float
    keep_original_audio: bool


@dataclass(slots=True)
class VideoRenderResult:
    """Per-event render result summary."""

    event_name: str
    mode: str
    outputs: list[Path]
    report_path: Path
    thumbnail_path: Path | None


@dataclass(slots=True)
class RenderProfile:
    """Resolved render profile with mode-specific values."""

    mode: str
    input_bucket: str
    output_bucket: str
    width: int
    height: int
    fps: int
    target_duration: float
    minimum_duration: float
    maximum_duration: float
    clip_min: float
    clip_max: float
    transition_duration: float
    fit_mode: str
    stabilization_enabled: bool
    keep_original_audio: bool
    dry_run: bool
    opening_title_seconds: float
    color_preset: str
    transition_probabilities: dict[str, float]
    duck_original_audio: float
    music_enabled: bool


class UnifiedVideoProcessingEngine:
    """One reusable implementation for short and long video rendering."""

    _video_extensions = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}

    def __init__(
        self,
        settings: Settings,
        command_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        random_seed: int | None = None,
    ) -> None:
        """Initialize engine with settings and pluggable command execution."""
        self._settings = settings
        self._rng = random.Random(random_seed)
        self._run_command = command_runner if command_runner is not None else self._default_run_command
        self._raw_config = self._read_raw_config()
        self._color_values = resolve_color_preset(settings=settings, raw_config=self._raw_config)

    def render(
        self,
        mode: str,
        event_name: str | None = None,
        profile: str | None = None,
        dry_run: bool = False,
    ) -> list[VideoRenderResult]:
        """Render short or long videos for one or more events."""
        normalized_mode = mode.strip().lower()
        render_profile = self._resolve_profile(mode=normalized_mode, profile_name=profile, dry_run=dry_run)

        events = [event_name] if event_name else self._discover_events()
        results: list[VideoRenderResult] = []

        for event in events:
            if event is None:
                continue
            result = self._render_event(event_name=event, render_profile=render_profile)
            if result is not None:
                results.append(result)

        return results

    def _render_event(self, event_name: str, render_profile: RenderProfile) -> VideoRenderResult | None:
        """Render all outputs for one event according to resolved profile."""
        started_at = time.perf_counter()

        source_dir = self._settings.project_root / self._settings.paths.input / event_name / render_profile.input_bucket
        if not source_dir.exists() or not source_dir.is_dir():
            logger.warning("Skipped event with missing source folder | event={} folder={}", event_name, source_dir)
            return None

        source_files = sorted(
            path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in self._video_extensions
        )
        if not source_files:
            logger.warning("Skipped event with no source videos | event={} folder={}", event_name, source_dir)
            return None

        logger.info("Analyzing Videos | event={} mode={} files={}", event_name, render_profile.mode, len(source_files))
        event_started = time.perf_counter()

        metadata = self._analyze_sources(source_files)
        if not metadata:
            logger.warning("Skipped event because all source analysis failed | event={}", event_name)
            return None

        clip_usage_state = self._load_clip_usage_state()
        available_clips = self._build_clip_candidates(metadata=metadata, profile=render_profile)
        if not available_clips:
            logger.warning("Skipped event because no usable clips were generated | event={}", event_name)
            return None

        timelines = self._build_timelines(
            event_name=event_name,
            profile=render_profile,
            available_clips=available_clips,
            clip_usage_state=clip_usage_state,
        )
        if not timelines:
            logger.warning("Skipped event because timeline generation returned no plans | event={}", event_name)
            return None

        output_root = self._settings.project_root / self._settings.paths.output / render_profile.output_bucket / event_name
        output_root.mkdir(parents=True, exist_ok=True)

        music_plan = self._build_music_plan(total_duration=max(plan.total_duration for plan in timelines), enabled=render_profile.music_enabled)

        rendered_outputs: list[Path] = []
        render_reports: list[dict[str, Any]] = []
        failed_jobs: list[dict[str, Any]] = []

        for plan in timelines:
            output_file = self._output_filename(profile=render_profile, event_name=event_name, output_index=plan.output_index)
            output_path = output_root / output_file

            logger.info(
                "Rendering Timeline | event={} mode={} output={} clips={} dry_run={}",
                event_name,
                render_profile.mode,
                output_file,
                len(plan.clips),
                render_profile.dry_run,
            )

            timeline_started = time.perf_counter()
            if not render_profile.dry_run:
                try:
                    self._render_timeline_with_recovery(
                        timeline=plan,
                        profile=render_profile,
                        output_path=output_path,
                        event_name=event_name,
                        music_plan=music_plan,
                    )
                except Exception as exc:  # noqa: BLE001
                    failed = self._record_failed_job(
                        event_name=event_name,
                        mode=render_profile.mode,
                        output_path=output_path,
                        timeline=plan,
                        error=exc,
                    )
                    failed_jobs.append(failed)
                    logger.error("Render failed after retry | event={} output={} error={}", event_name, output_file, exc)
                    continue
            timeline_seconds = time.perf_counter() - timeline_started

            if render_profile.dry_run:
                output_size = 0
            else:
                output_size = output_path.stat().st_size if output_path.exists() else 0

            rendered_outputs.append(output_path)
            render_reports.append(
                {
                    "output_file": str(output_path),
                    "clip_positions": [
                        {
                            "source": str(clip.source_path),
                            "start": round(clip.start, 3),
                            "duration": round(clip.duration, 3),
                            "segment_id": clip.segment_id,
                        }
                        for clip in plan.clips
                    ],
                    "transitions": [choice.label for choice in plan.transitions],
                    "music": [
                        {
                            "path": str(item["path"]),
                            "start": round(float(item["start"]), 3),
                            "use_seconds": round(float(item["use_seconds"]), 3),
                        }
                        for item in music_plan
                    ],
                    "timeline_duration": round(plan.total_duration, 3),
                    "render_time": round(timeline_seconds, 3),
                    "output_size": output_size,
                }
            )

        thumbnail_path: Path | None = None
        if render_profile.mode == "long" and self._settings.thumbnails.generate and timelines and timelines[0].clips:
            thumbnail_dir = self._settings.project_root / self._settings.paths.output / "thumbnails"
            thumbnail_dir.mkdir(parents=True, exist_ok=True)
            thumbnail_path = thumbnail_dir / f"{event_name}-thumbnail.jpg"
            if render_profile.dry_run:
                thumbnail_path.write_text("dry-run thumbnail placeholder", encoding="utf-8")
            else:
                self._write_thumbnail(timelines[0], thumbnail_path)

        if not render_profile.dry_run:
            self._apply_clip_usage_updates(clip_usage_state=clip_usage_state, timelines=timelines)
            self._save_clip_usage_state(clip_usage_state)

        report_dir = self._settings.project_root / self._settings.paths.reports
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "render_report.json"

        report_payload = {
            "event_name": event_name,
            "mode": render_profile.mode,
            "videos_used": [self._metadata_record(item) for item in metadata],
            "outputs": render_reports,
            "render_time_total": round(time.perf_counter() - event_started, 3),
            "gpu_used": self._gpu_used_label(),
            "dry_run": render_profile.dry_run,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "thumbnail": str(thumbnail_path) if thumbnail_path else None,
            "failed_jobs": failed_jobs,
            "summary": {
                "outputs_count": len(rendered_outputs),
                "failed_count": len(failed_jobs),
                "media_analyzed": len(metadata),
                "total_output_size": sum(int(item.get("output_size", 0)) for item in render_reports),
            },
        }

        write_report_artifacts(report_path=report_path, payload=report_payload)

        media_usage_path = report_dir / "media_usage.json"
        media_records: list[dict[str, Any]] = [{"path": str(item.path), "type": "video"} for item in metadata]
        for item in music_plan:
            media_records.append({"path": str(item["path"]), "type": "music"})
        update_media_usage(media_usage_path=media_usage_path, media_records=media_records, workflow=render_profile.mode)

        history_path = report_dir / "render_history.json"
        append_render_history(
            render_history_path=history_path,
            history_record={
                "render_date": datetime.now(timezone.utc).isoformat(),
                "event": event_name,
                "duration": round(time.perf_counter() - started_at, 3),
                "workflow": render_profile.mode,
                "files_used": [str(item.path) for item in metadata],
                "music_used": [str(item["path"]) for item in music_plan],
                "gpu_used": self._gpu_used_label(),
                "render_time": round(time.perf_counter() - started_at, 3),
                "output_size": sum(int(item.get("output_size", 0)) for item in render_reports),
            },
        )

        logger.success(
            "Completed event render | event={} mode={} outputs={} failed={} elapsed={:.3f}s",
            event_name,
            render_profile.mode,
            len(rendered_outputs),
            len(failed_jobs),
            time.perf_counter() - started_at,
        )

        return VideoRenderResult(
            event_name=event_name,
            mode=render_profile.mode,
            outputs=rendered_outputs,
            report_path=report_path,
            thumbnail_path=thumbnail_path,
        )

    def _resolve_profile(self, mode: str, profile_name: str | None, dry_run: bool) -> RenderProfile:
        """Resolve unified profile settings from base config and optional YAML overrides."""
        if mode not in {"short", "long"}:
            raise ValueError(f"Unsupported mode: {mode}")

        defaults = {
            "short": {
                "input_bucket": "shortform_videos",
                "output_bucket": "shorts",
                "width": self._settings.shorts.resolution.width,
                "height": self._settings.shorts.resolution.height,
                "fps": self._settings.shorts.fps,
                "target_duration": float(self._settings.shorts.duration.default),
                "minimum_duration": float(self._settings.shorts.duration.minimum),
                "maximum_duration": float(self._settings.shorts.duration.maximum),
                "opening_title_seconds": float(self._settings.text_overlay.duration),
            },
            "long": {
                "input_bucket": "longform_videos",
                "output_bucket": "long",
                "width": self._settings.long.resolution.width,
                "height": self._settings.long.resolution.height,
                "fps": self._settings.long.fps,
                "target_duration": float(self._settings.long.duration.default),
                "minimum_duration": float(self._settings.long.duration.minimum),
                "maximum_duration": float(self._settings.long.duration.maximum),
                "opening_title_seconds": 0.0,
            },
        }

        cfg: dict[str, Any] = {
            **defaults[mode],
            "clip_min": float(self._settings.videos.clip_duration.minimum),
            "clip_max": float(self._settings.videos.clip_duration.maximum),
            "transition_duration": float(self._settings.transitions.duration),
            "fit_mode": "center_crop",
            "stabilization_enabled": False,
            "keep_original_audio": not bool(self._settings.videos.mute_original_audio),
            "duck_original_audio": 0.35,
            "music_enabled": True,
            "color_preset": "natural",
            "transition_probabilities": {
                "hard_cut": 0.1,
                "cross_dissolve": 0.4,
                "film_burn": 0.1,
                "fade_through_black": 0.2,
                "zoom": 0.1,
                "slide": 0.05,
                "blur": 0.05,
            },
        }

        top = self._raw_config.get("video_render")
        if isinstance(top, dict):
            cfg.update({
                "clip_min": float(top.get("clip_min", cfg["clip_min"])),
                "clip_max": float(top.get("clip_max", cfg["clip_max"])),
                "fit_mode": str(top.get("fit_mode", cfg["fit_mode"])),
                "stabilization_enabled": bool(top.get("stabilization_enabled", cfg["stabilization_enabled"])),
                "keep_original_audio": bool(top.get("keep_original_audio", cfg["keep_original_audio"])),
                "duck_original_audio": float(top.get("duck_original_audio", cfg["duck_original_audio"])),
                "music_enabled": bool(top.get("music_enabled", cfg["music_enabled"])),
                "color_preset": str(top.get("color_preset", cfg["color_preset"])),
            })
            transition_probabilities = top.get("transition_probabilities")
            if isinstance(transition_probabilities, dict):
                cfg["transition_probabilities"] = {
                    key: max(0.0, float(value))
                    for key, value in transition_probabilities.items()
                    if isinstance(key, str)
                }
            mode_top = top.get(mode)
            if isinstance(mode_top, dict):
                cfg.update(mode_top)

            profiles = top.get("profiles")
            if profile_name and isinstance(profiles, dict):
                selected = profiles.get(profile_name)
                if isinstance(selected, dict):
                    cfg.update({k: v for k, v in selected.items() if not isinstance(v, dict)})
                    mode_selected = selected.get(mode)
                    if isinstance(mode_selected, dict):
                        cfg.update(mode_selected)

        minimum_duration = float(cfg["minimum_duration"])
        maximum_duration = float(cfg["maximum_duration"])
        target_duration = _clamp(float(cfg["target_duration"]), minimum_duration, maximum_duration)

        clip_min = max(0.8, float(cfg["clip_min"]))
        clip_max = max(clip_min, float(cfg["clip_max"]))

        return RenderProfile(
            mode=mode,
            input_bucket=str(cfg["input_bucket"]),
            output_bucket=str(cfg["output_bucket"]),
            width=int(cfg["width"]),
            height=int(cfg["height"]),
            fps=max(1, int(cfg["fps"])),
            target_duration=target_duration,
            minimum_duration=minimum_duration,
            maximum_duration=maximum_duration,
            clip_min=clip_min,
            clip_max=clip_max,
            transition_duration=_clamp(float(cfg["transition_duration"]), 0.0, 1.5),
            fit_mode=str(cfg["fit_mode"]),
            stabilization_enabled=bool(cfg["stabilization_enabled"]),
            keep_original_audio=bool(cfg["keep_original_audio"]),
            dry_run=dry_run,
            opening_title_seconds=max(0.0, float(cfg["opening_title_seconds"])),
            color_preset=str(cfg["color_preset"]).strip().lower(),
            transition_probabilities={str(key): float(value) for key, value in dict(cfg["transition_probabilities"]).items()},
            duck_original_audio=_clamp(float(cfg["duck_original_audio"]), 0.0, 1.0),
            music_enabled=bool(cfg["music_enabled"]),
        )

    def _discover_events(self) -> list[str]:
        """Discover event folders under configured input root."""
        input_root = self._settings.project_root / self._settings.paths.input
        if not input_root.exists() or not input_root.is_dir():
            return []
        return sorted(item.name for item in input_root.iterdir() if item.is_dir())

    def _analyze_sources(self, source_files: list[Path]) -> list[VideoMetadata]:
        """Collect metadata for all sources and skip failed probes."""
        collected: list[VideoMetadata] = []
        for source in source_files:
            item = self._analyze_video(source)
            if item is None:
                logger.warning("Skipping source that failed analysis | source={}", source)
                continue
            collected.append(item)
        return collected

    def _analyze_video(self, source: Path) -> VideoMetadata | None:
        """Analyze one source video with ffprobe and return normalized metadata."""
        command = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(source),
        ]
        completed = self._run_command(command)
        if completed.returncode != 0:
            return None

        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return None

        streams = payload.get("streams")
        if not isinstance(streams, list):
            return None

        video_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), None)
        if not isinstance(video_stream, dict):
            return None

        audio_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"), None)

        width = int(video_stream.get("width", 0) or 0)
        height = int(video_stream.get("height", 0) or 0)
        codec = str(video_stream.get("codec_name", "unknown"))

        frame_rate_raw = str(video_stream.get("r_frame_rate", "0/1"))
        fps = _fraction_to_float(frame_rate_raw)

        tags = video_stream.get("tags") if isinstance(video_stream.get("tags"), dict) else {}
        side_data = video_stream.get("side_data_list") if isinstance(video_stream.get("side_data_list"), list) else []
        rotation = _read_rotation(tags=tags, side_data=side_data)

        format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
        duration = _safe_float(format_data.get("duration"), 0.0)
        bitrate = int(_safe_float(format_data.get("bit_rate"), 0.0))

        if rotation in {90, 270}:
            width, height = height, width

        orientation = "portrait" if height > width else "landscape"

        return VideoMetadata(
            path=source,
            width=width,
            height=height,
            fps=fps,
            duration=max(0.1, duration),
            codec=codec,
            rotation=rotation,
            has_audio=audio_stream is not None,
            bitrate=max(0, bitrate),
            orientation=orientation,
        )

    def _build_clip_candidates(self, metadata: list[VideoMetadata], profile: RenderProfile) -> list[ClipSegment]:
        """Build candidate segments for each source video with random clip extraction."""
        candidates: list[ClipSegment] = []
        seen_ids: set[str] = set()

        for item in metadata:
            if item.duration <= profile.clip_max:
                segment = ClipSegment(
                    source_path=item.path,
                    start=0.0,
                    duration=item.duration,
                    segment_id=self._segment_id(item.path, 0.0, item.duration),
                    has_audio=item.has_audio,
                )
                if segment.segment_id not in seen_ids:
                    candidates.append(segment)
                    seen_ids.add(segment.segment_id)
                continue

            average = max(0.5, (profile.clip_min + profile.clip_max) / 2.0)
            sample_count = max(2, int(item.duration / average))
            for _ in range(sample_count):
                segment_duration = self._rng.uniform(profile.clip_min, profile.clip_max)
                segment_duration = min(segment_duration, item.duration)
                max_start = max(0.0, item.duration - segment_duration)
                segment_start = self._rng.uniform(0.0, max_start) if max_start > 0 else 0.0
                segment_id = self._segment_id(item.path, segment_start, segment_duration)
                if segment_id in seen_ids:
                    continue
                candidates.append(
                    ClipSegment(
                        source_path=item.path,
                        start=segment_start,
                        duration=segment_duration,
                        segment_id=segment_id,
                        has_audio=item.has_audio,
                    )
                )
                seen_ids.add(segment_id)

        return candidates

    def _build_timelines(
        self,
        event_name: str,
        profile: RenderProfile,
        available_clips: list[ClipSegment],
        clip_usage_state: dict[str, Any],
    ) -> list[TimelinePlan]:
        """Build timeline plans using distribution rules and persistent clip usage memory."""
        usage_counts = clip_usage_state.setdefault("clips", {})
        if not isinstance(usage_counts, dict):
            usage_counts = {}
            clip_usage_state["clips"] = usage_counts

        grouped = self._group_clips_by_source(available_clips, usage_counts)
        if not grouped:
            return []

        if profile.mode == "long":
            clips = self._select_clips_for_part(
                grouped=grouped,
                usage_counts=usage_counts,
                target_duration=profile.target_duration,
                minimum_duration=profile.minimum_duration,
            )
            if not clips:
                return []
            transitions = self._select_transitions(
                len(clips) - 1,
                transition_duration=profile.transition_duration,
                probabilities=profile.transition_probabilities,
            )
            duration = _timeline_duration(clips, transitions)
            keep_audio = profile.keep_original_audio and all(clip.has_audio for clip in clips)
            return [
                TimelinePlan(
                    event_name=event_name,
                    mode=profile.mode,
                    output_index=1,
                    clips=clips,
                    transitions=transitions,
                    total_duration=duration,
                    keep_original_audio=keep_audio,
                )
            ]

        timelines: list[TimelinePlan] = []
        output_index = 1
        while True:
            clips = self._select_clips_for_part(
                grouped=grouped,
                usage_counts=usage_counts,
                target_duration=profile.target_duration,
                minimum_duration=profile.minimum_duration,
            )
            if not clips:
                break
            transitions = self._select_transitions(
                len(clips) - 1,
                transition_duration=profile.transition_duration,
                probabilities=profile.transition_probabilities,
            )
            duration = _timeline_duration(clips, transitions)
            keep_audio = profile.keep_original_audio and all(clip.has_audio for clip in clips)
            timelines.append(
                TimelinePlan(
                    event_name=event_name,
                    mode=profile.mode,
                    output_index=output_index,
                    clips=clips,
                    transitions=transitions,
                    total_duration=duration,
                    keep_original_audio=keep_audio,
                )
            )
            output_index += 1

            if self._remaining_unique_duration(grouped) < profile.clip_min:
                break

        return timelines

    def _group_clips_by_source(
        self,
        clips: list[ClipSegment],
        usage_counts: dict[str, Any],
    ) -> dict[str, deque[ClipSegment]]:
        """Group clips by source and sort with unused-first strategy."""
        grouped: dict[str, list[ClipSegment]] = {}
        for clip in clips:
            key = str(clip.source_path)
            grouped.setdefault(key, []).append(clip)

        result: dict[str, deque[ClipSegment]] = {}
        for source, items in grouped.items():
            ordered = sorted(
                items,
                key=lambda clip: (int(usage_counts.get(clip.segment_id, 0)), clip.start),
            )
            result[source] = deque(ordered)
        return result

    def _select_clips_for_part(
        self,
        grouped: dict[str, deque[ClipSegment]],
        usage_counts: dict[str, Any],
        target_duration: float,
        minimum_duration: float,
    ) -> list[ClipSegment]:
        """Select clips with source distribution and no consecutive same-source preference."""
        selected: list[ClipSegment] = []
        selected_duration = 0.0
        last_source: str | None = None

        source_order = sorted(grouped.keys(), key=lambda source: self._source_priority(grouped[source], usage_counts))
        if self._settings.videos.shuffle:
            self._rng.shuffle(source_order)

        while selected_duration < target_duration:
            picked = self._pick_next_clip(grouped=grouped, source_order=source_order, last_source=last_source)
            if picked is None:
                break
            selected.append(picked)
            selected_duration += picked.duration
            last_source = str(picked.source_path)

        if selected_duration < minimum_duration:
            reuse_pool = self._build_reuse_pool(grouped, usage_counts)
            attempts = 0
            while selected_duration < minimum_duration and reuse_pool and attempts < 1000:
                attempts += 1
                candidate = self._pick_reuse_candidate(reuse_pool, last_source)
                if candidate is None:
                    break
                selected.append(candidate)
                selected_duration += candidate.duration
                last_source = str(candidate.source_path)

        return selected

    def _pick_next_clip(
        self,
        grouped: dict[str, deque[ClipSegment]],
        source_order: list[str],
        last_source: str | None,
    ) -> ClipSegment | None:
        """Pick next unique clip while trying to avoid consecutive same-source clips."""
        for source in source_order:
            queue = grouped[source]
            if not queue:
                continue
            if source == last_source and self._has_alternative(grouped, exclude=source):
                continue
            return queue.popleft()

        for source in source_order:
            queue = grouped[source]
            if queue:
                return queue.popleft()

        return None

    def _has_alternative(self, grouped: dict[str, deque[ClipSegment]], exclude: str) -> bool:
        """Check if an alternative source still has unused clips."""
        return any(source != exclude and bool(queue) for source, queue in grouped.items())

    def _build_reuse_pool(
        self,
        grouped: dict[str, deque[ClipSegment]],
        usage_counts: dict[str, Any],
    ) -> list[ClipSegment]:
        """Create reuse pool from remaining and historical clips sorted by least usage."""
        pool: list[ClipSegment] = []
        for queue in grouped.values():
            pool.extend(list(queue))

        pool.sort(key=lambda clip: (int(usage_counts.get(clip.segment_id, 0)), self._rng.random()))
        return pool

    def _pick_reuse_candidate(self, pool: list[ClipSegment], last_source: str | None) -> ClipSegment | None:
        """Pick reusable clip while avoiding immediate same-source repetition when possible."""
        for index, clip in enumerate(pool):
            source = str(clip.source_path)
            if source == last_source and len(pool) > 1:
                continue
            return pool.pop(index)
        if pool:
            return pool.pop(0)
        return None

    def _remaining_unique_duration(self, grouped: dict[str, deque[ClipSegment]]) -> float:
        """Compute duration left in unique unused clip queues."""
        return sum(clip.duration for queue in grouped.values() for clip in queue)

    def _select_transitions(
        self,
        count: int,
        transition_duration: float,
        probabilities: dict[str, float],
    ) -> list[TransitionChoice]:
        """Select transitions for clip boundaries with immediate-repeat avoidance."""
        if count <= 0:
            return []

        options = self._enabled_transitions(transition_duration=transition_duration)
        if not options:
            options = [("hard_cut", "fade", 0.001)]

        transitions: list[TransitionChoice] = []
        last_label: str | None = None

        for _ in range(count):
            candidates = [item for item in options if item[0] != last_label]
            if not candidates:
                candidates = options
            weights = [max(0.0, float(probabilities.get(item[0], 1.0))) for item in candidates]
            if sum(weights) <= 0:
                label, ffmpeg_name, duration = self._rng.choice(candidates)
            else:
                label, ffmpeg_name, duration = self._rng.choices(candidates, weights=weights, k=1)[0]
            transitions.append(TransitionChoice(label=label, ffmpeg_name=ffmpeg_name, duration=duration))
            last_label = label

        return transitions

    def _enabled_transitions(self, transition_duration: float) -> list[tuple[str, str, float]]:
        """Build enabled transition choices from YAML flags."""
        enabled: list[tuple[str, str, float]] = []

        if self._settings.transitions.hard_cut:
            enabled.append(("hard_cut", "fade", 0.001))
        if self._settings.transitions.cross_dissolve:
            enabled.append(("cross_dissolve", "fade", transition_duration))
        if self._settings.transitions.film_burn:
            enabled.append(("film_burn", "fadefast", transition_duration))

        # Mapped from requirement names to ffmpeg xfade transitions.
        enabled.append(("fade_through_black", "fadeblack", transition_duration))
        enabled.append(("simple_match_cut", "smoothleft", transition_duration))
        enabled.append(("zoom", "zoomin", transition_duration))
        enabled.append(("slide", "slideleft", transition_duration))
        enabled.append(("blur", "hblur", transition_duration))

        return enabled

    def _render_timeline_with_recovery(
        self,
        timeline: TimelinePlan,
        profile: RenderProfile,
        output_path: Path,
        event_name: str,
        music_plan: list[dict[str, Any]],
    ) -> None:
        """Render once and retry one time before failing the job."""
        attempt = 1
        while attempt <= 2:
            try:
                self._render_timeline(
                    timeline=timeline,
                    profile=profile,
                    output_path=output_path,
                    event_name=event_name,
                    music_plan=music_plan,
                )
                return
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    raise
                logger.warning("Render failed, retrying once | output={} attempt={} error={}", output_path, attempt, exc)
                attempt += 1

    def _render_timeline(
        self,
        timeline: TimelinePlan,
        profile: RenderProfile,
        output_path: Path,
        event_name: str,
        music_plan: list[dict[str, Any]],
    ) -> None:
        """Render one timeline using ffmpeg stream-based clip extraction."""
        command: list[str] = [self._settings.render.ffmpeg_path, "-y"]

        if self._settings.render.gpu_auto_detect:
            command.extend(["-hwaccel", "auto"])

        for clip in timeline.clips:
            command.extend(
                [
                    "-ss",
                    str(round(clip.start, 3)),
                    "-t",
                    str(round(clip.duration, 3)),
                    "-i",
                    str(clip.source_path),
                ]
            )

        for plan in music_plan:
            command.extend(["-ss", str(round(float(plan["start"]), 3)), "-i", str(plan["path"])])

        filter_video = self._build_video_filter(
            timeline=timeline,
            profile=profile,
            event_name=event_name,
        )

        audio_filter, audio_map = self._build_audio_filter(
            timeline=timeline,
            music_plan=music_plan,
            profile=profile,
        )

        filter_complex = filter_video if not audio_filter else f"{filter_video};{audio_filter}"
        command.extend(["-filter_complex", filter_complex, "-map", "[vout]"])

        if audio_map:
            command.extend(["-map", audio_map])
        else:
            command.append("-an")

        command.extend(
            [
                "-r",
                str(profile.fps),
                "-c:v",
                self._video_codec(),
                "-threads",
                str(max(1, int(self._settings.render.workers))),
                "-preset",
                "p5" if self._gpu_used_label() != "cpu" else "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        completed = self._run_command(command)
        if completed.returncode == 0:
            return

        if self._gpu_used_label() != "cpu":
            logger.warning("GPU render failed, retrying with CPU fallback | output={}", output_path)
            cpu_command = self._force_cpu_codec(command)
            completed_cpu = self._run_command(cpu_command)
            if completed_cpu.returncode == 0:
                return
            raise RuntimeError(f"ffmpeg render failed for {output_path}: {completed_cpu.stderr}")

        raise RuntimeError(f"ffmpeg render failed for {output_path}: {completed.stderr}")

    def _build_video_filter(self, timeline: TimelinePlan, profile: RenderProfile, event_name: str) -> str:
        """Build filter graph for video scaling, grading, stabilization, transitions, and overlays."""
        parts: list[str] = []
        labels: list[str] = []

        values = self._resolve_color_values(profile)

        for index, _clip in enumerate(timeline.clips):
            label = f"v{index}"
            chain = (
                f"[{index}:v]"
                f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=increase,"
                f"crop={profile.width}:{profile.height},"
                f"fps={profile.fps},"
                f"eq=brightness={values.brightness}:contrast={values.contrast}:saturation={values.saturation}:gamma={values.gamma},"
                f"unsharp=5:5:{values.sharpen}"
            )
            if profile.stabilization_enabled:
                chain = f"{chain},deshake"
            chain = f"{chain},setsar=1,format=yuv420p[{label}]"
            parts.append(chain)
            labels.append(label)

        current = labels[0]
        elapsed = timeline.clips[0].duration
        for index in range(1, len(labels)):
            transition = timeline.transitions[index - 1]
            out = f"x{index}"
            offset = max(0.0, elapsed - transition.duration)
            parts.append(
                f"[{current}][{labels[index]}]xfade=transition={transition.ffmpeg_name}:duration={transition.duration}:offset={offset}[{out}]"
            )
            current = out
            elapsed += timeline.clips[index].duration - transition.duration

        parts.append(
            self._overlay_chain(
                mode=timeline.mode,
                source_label=current,
                profile=profile,
                event_name=event_name,
                total_duration=timeline.total_duration,
            )
        )
        return ";".join(parts)

    def _overlay_chain(
        self,
        mode: str,
        source_label: str,
        profile: RenderProfile,
        event_name: str,
        total_duration: float,
    ) -> str:
        """Build mode-specific overlays and title chain ending at [vout]."""
        parts: list[str] = []
        current = source_label

        if mode == "short":
            header = self._settings.project_root / self._settings.overlays.header.file
            footer = self._settings.project_root / self._settings.overlays.footer.file
            if self._settings.overlays.header.enabled and header.exists():
                parts.append(f"movie={_ff_escape(str(header))},format=rgba[h1]")
                parts.append(f"[{current}][h1]overlay=x=(W-w)/2:y={self._settings.overlays.header.margin_top}:format=auto[vh]")
                current = "vh"
            if self._settings.overlays.footer.enabled and footer.exists():
                footer_y = f"H-h-{self._settings.overlays.footer.margin_bottom}"
                parts.append(f"movie={_ff_escape(str(footer))},format=rgba[f1]")
                parts.append(f"[{current}][f1]overlay=x=(W-w)/2:y={footer_y}:format=auto[vf]")
                current = "vf"

            if profile.opening_title_seconds > 0:
                title = _ff_escape(event_name.upper())
                font_path = _ff_escape(str(self._settings.project_root / self._settings.text_overlay.font))
                seconds = profile.opening_title_seconds
                parts.append(
                    f"[{current}]drawtext=fontfile='{font_path}':text='{title}':"
                    f"fontsize=84:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
                    f"shadowx=3:shadowy=3:shadowcolor=black@0.5:"
                    f"alpha='if(lt(t,1),t/1,if(lt(t,{max(2.0, seconds - 1.0)}),1,if(lt(t,{seconds}),({seconds}-t)/1,0)))'[vout]"
                )
            else:
                parts.append(f"[{current}]copy[vout]")
            return ";".join(parts)

        socials = self._settings.project_root / self._settings.overlays.socials.file
        website = self._settings.project_root / self._settings.overlays.website.file

        if self._settings.overlays.socials.enabled and socials.exists():
            parts.append(f"movie={_ff_escape(str(socials))},format=rgba[s1]")
            parts.append(f"[{current}][s1]overlay={self._settings.overlays.socials.margin_left}:{self._settings.overlays.socials.margin_top}:format=auto[vs]")
            current = "vs"

        if self._settings.overlays.website.enabled and website.exists():
            right_margin = self._settings.overlays.website.margin_right
            top_margin = self._settings.overlays.website.margin_top
            parts.append(f"movie={_ff_escape(str(website))},format=rgba[w1]")
            parts.append(f"[{current}][w1]overlay=W-w-{right_margin}:{top_margin}:format=auto[vw]")
            current = "vw"

        ending_start = max(0.0, total_duration - 5.0)
        font_path = _ff_escape(str(self._settings.project_root / self._settings.text_overlay.font))
        ending_text = _ff_escape(self._settings.text_overlay.opening_title)
        parts.append(
            f"[{current}]"
            f"drawtext=fontfile='{font_path}':text='{ending_text}':"
            f"fontsize=66:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
            f"shadowx=3:shadowy=3:shadowcolor=black@0.45:enable='gte(t,{ending_start})',"
            f"fade=t=out:st={ending_start}:d=5[vout]"
        )

        return ";".join(parts)

    def _build_audio_filter(
        self,
        timeline: TimelinePlan,
        music_plan: list[dict[str, Any]],
        profile: RenderProfile,
    ) -> tuple[str, str | None]:
        """Build audio chain combining optional source audio and random music."""
        parts: list[str] = []

        source_audio_label: str | None = None
        if timeline.keep_original_audio:
            chain = self._build_source_audio_chain(
                timeline=timeline,
                crossfade=self._settings.audio.crossfade,
                duck_level=profile.duck_original_audio,
            )
            if chain:
                parts.extend(chain)
                source_audio_label = "asrc"

        music_audio_label: str | None = None
        if music_plan:
            chain = self._build_music_audio_chain(
                timeline=timeline,
                music_plan=music_plan,
                profile=profile,
            )
            if chain:
                parts.extend(chain)
                music_audio_label = "amus"

        if source_audio_label and music_audio_label:
            parts.append(
                f"[{source_audio_label}][{music_audio_label}]amix=inputs=2:duration=first:dropout_transition=2,"
                f"loudnorm=I=-16:LRA=11:TP=-1.5[aout]"
            )
            return ";".join(parts), "[aout]"

        if source_audio_label:
            parts.append(f"[{source_audio_label}]anull[aout]")
            return ";".join(parts), "[aout]"

        if music_audio_label:
            parts.append(f"[{music_audio_label}]anull[aout]")
            return ";".join(parts), "[aout]"

        return "", None

    def _build_source_audio_chain(self, timeline: TimelinePlan, crossfade: float, duck_level: float) -> list[str]:
        """Build optional source-audio chain from timeline clips."""
        parts: list[str] = []
        labels: list[str] = []

        for index, clip in enumerate(timeline.clips):
            if not clip.has_audio:
                continue
            label = f"sa{index}"
            parts.append(f"[{index}:a]atrim=0:{clip.duration},asetpts=PTS-STARTPTS[{label}]")
            labels.append(label)

        if not labels:
            return []

        current = labels[0]
        fade = _clamp(float(crossfade), 0.0, 2.0)
        for index in range(1, len(labels)):
            out = f"sax{index}"
            if fade <= 0:
                parts.append(f"[{current}][{labels[index]}]concat=n=2:v=0:a=1[{out}]")
            else:
                parts.append(f"[{current}][{labels[index]}]acrossfade=d={fade}:c1=tri:c2=tri[{out}]")
            current = out

        parts.append(f"[{current}]volume={_clamp(duck_level, 0.0, 1.0)}[asrc]")
        return parts

    def _build_music_audio_chain(
        self,
        timeline: TimelinePlan,
        music_plan: list[dict[str, Any]],
        profile: RenderProfile,
    ) -> list[str]:
        """Build music chain with crossfades and loudness normalization."""
        parts: list[str] = []
        labels: list[str] = []

        base_index = len(timeline.clips)
        for index, track in enumerate(music_plan):
            input_index = base_index + index
            label = f"ma{index}"
            use_seconds = float(track["use_seconds"])
            parts.append(f"[{input_index}:a]atrim=0:{use_seconds},asetpts=PTS-STARTPTS[{label}]")
            labels.append(label)

        if not labels:
            return []

        current = labels[0]
        crossfade = _clamp(self._settings.audio.crossfade, 0.0, 4.0)
        for index in range(1, len(labels)):
            out = f"max{index}"
            if crossfade <= 0:
                parts.append(f"[{current}][{labels[index]}]concat=n=2:v=0:a=1[{out}]")
            else:
                parts.append(f"[{current}][{labels[index]}]acrossfade=d={crossfade}:c1=tri:c2=tri[{out}]")
            current = out

        fade_in = _clamp(self._settings.audio.fade_in, 0.0, 5.0)
        fade_out = _clamp(self._settings.audio.fade_out, 0.0, 5.0)
        fade_out_start = max(0.0, timeline.total_duration - fade_out)
        volume = _clamp(self._settings.audio.music_volume, 0.0, 1.0)

        parts.append(
            f"[{current}]"
            f"atrim=0:{timeline.total_duration},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={fade_out_start}:d={fade_out},"
            f"volume={volume},loudnorm=I=-16:LRA=11:TP=-1.5[amus]"
        )

        return parts

    def _build_music_plan(self, total_duration: float, enabled: bool) -> list[dict[str, Any]]:
        """Build random music plan that covers the timeline duration."""
        if not enabled:
            return []
        music_files = self._list_music_files()
        if not music_files:
            return []

        required = total_duration + _clamp(self._settings.audio.crossfade, 0.0, 4.0)
        accumulated = 0.0
        plans: list[dict[str, Any]] = []

        while accumulated < required and len(plans) < 24:
            track = self._rng.choice(music_files)
            duration = self._probe_audio_duration(track)
            if duration <= 0.5:
                break

            if self._settings.audio.random_start_position:
                start = self._rng.uniform(0.0, max(0.0, duration * 0.5))
            else:
                start = 0.0
            usable = max(0.5, duration - start)
            use_seconds = min(usable, required - accumulated + self._settings.audio.crossfade)

            plans.append({"path": track, "start": start, "use_seconds": use_seconds})
            accumulated += max(0.1, use_seconds - self._settings.audio.crossfade)

        return plans

    def _list_music_files(self) -> list[Path]:
        """List available background music files."""
        music_dir = self._settings.project_root / self._settings.paths.music
        if not music_dir.exists() or not music_dir.is_dir():
            return []

        supported = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
        return sorted(path for path in music_dir.iterdir() if path.is_file() and path.suffix.lower() in supported)

    def _probe_audio_duration(self, audio_path: Path) -> float:
        """Probe audio duration and fallback to conservative estimate."""
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        completed = self._run_command(command)
        if completed.returncode == 0:
            try:
                return float((completed.stdout or "").strip())
            except ValueError:
                pass

        size_mb = audio_path.stat().st_size / (1024 * 1024)
        return max(30.0, size_mb * 8.0)

    def _write_thumbnail(self, timeline: TimelinePlan, thumbnail_path: Path) -> None:
        """Generate long-video thumbnail from timeline middle clip source frame."""
        middle = timeline.clips[len(timeline.clips) // 2]
        width = self._settings.thumbnails.width
        height = self._settings.thumbnails.height

        command = [
            self._settings.render.ffmpeg_path,
            "-y",
            "-ss",
            str(round(middle.start, 3)),
            "-i",
            str(middle.source_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            "-q:v",
            "2",
            str(thumbnail_path),
        ]
        completed = self._run_command(command)
        if completed.returncode != 0:
            raise RuntimeError(f"Thumbnail generation failed: {completed.stderr}")

    def _record_failed_job(
        self,
        event_name: str,
        mode: str,
        output_path: Path,
        timeline: TimelinePlan,
        error: Exception,
    ) -> dict[str, Any]:
        """Persist failed job descriptor and return report record."""
        failed_root = self._settings.project_root / self._settings.paths.output / "failed"
        failed_root.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        failed_file = failed_root / f"{output_path.stem}-{stamp}.json"
        payload = {
            "event": event_name,
            "mode": mode,
            "output": str(output_path),
            "error": str(error),
            "clip_positions": [
                {
                    "source": str(clip.source_path),
                    "start": round(clip.start, 3),
                    "duration": round(clip.duration, 3),
                    "segment_id": clip.segment_id,
                }
                for clip in timeline.clips
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        failed_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def _load_clip_usage_state(self) -> dict[str, Any]:
        """Load clip usage memory for unused-first future renders."""
        usage_path = self._clip_usage_path()
        if not usage_path.exists():
            return {"clips": {}}

        try:
            data = json.loads(usage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"clips": {}}

        if not isinstance(data, dict):
            return {"clips": {}}
        if not isinstance(data.get("clips"), dict):
            data["clips"] = {}
        return data

    def _save_clip_usage_state(self, clip_usage_state: dict[str, Any]) -> None:
        """Persist clip usage memory to output reports folder."""
        usage_path = self._clip_usage_path()
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        clip_usage_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        usage_path.write_text(json.dumps(clip_usage_state, indent=2), encoding="utf-8")

    def _apply_clip_usage_updates(self, clip_usage_state: dict[str, Any], timelines: list[TimelinePlan]) -> None:
        """Update usage counters for rendered clip segments."""
        clips = clip_usage_state.setdefault("clips", {})
        if not isinstance(clips, dict):
            clips = {}
            clip_usage_state["clips"] = clips

        for timeline in timelines:
            for clip in timeline.clips:
                current = int(clips.get(clip.segment_id, 0))
                clips[clip.segment_id] = current + 1

    def _clip_usage_path(self) -> Path:
        """Return clip usage memory path."""
        return self._settings.project_root / self._settings.paths.output / "reports" / "clip_usage.json"

    def _source_priority(self, queue: deque[ClipSegment], usage_counts: dict[str, Any]) -> tuple[int, float]:
        """Sort source queues by least-used next segment and queue size."""
        if not queue:
            return (10_000, 0.0)
        first = queue[0]
        used = int(usage_counts.get(first.segment_id, 0))
        return (used, -float(len(queue)))

    def _output_filename(self, profile: RenderProfile, event_name: str, output_index: int) -> str:
        """Build output file names for short and long modes."""
        if profile.mode == "short":
            return f"{event_name}-short-video-part{output_index:02d}.mp4"
        return f"{event_name}-long-video.mp4"

    def _segment_id(self, path: Path, start: float, duration: float) -> str:
        """Create deterministic segment identifier for usage memory."""
        return f"{path}|{start:.3f}|{duration:.3f}"

    def _metadata_record(self, metadata: VideoMetadata) -> dict[str, Any]:
        """Serialize metadata entry for render report."""
        return {
            "path": str(metadata.path),
            "resolution": f"{metadata.width}x{metadata.height}",
            "fps": round(metadata.fps, 3),
            "duration": round(metadata.duration, 3),
            "codec": metadata.codec,
            "rotation": metadata.rotation,
            "audio": metadata.has_audio,
            "bitrate": metadata.bitrate,
            "orientation": metadata.orientation,
        }

    def _read_raw_config(self) -> dict[str, Any]:
        """Read raw YAML payload for optional untyped overrides."""
        try:
            payload = yaml.safe_load(self._settings.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _video_codec(self) -> str:
        """Select output codec using configured encoder preference."""
        preferred = self._settings.render.preferred_encoder.strip().lower()
        mapping = {
            "nvidia": "h264_nvenc",
            "videotoolbox": "h264_videotoolbox",
            "quicksync": "h264_qsv",
            "amd": "h264_amf",
            "cpu": "libx264",
            "auto": "libx264",
        }
        return mapping.get(preferred, "libx264")

    def _force_cpu_codec(self, command: list[str]) -> list[str]:
        """Replace accelerated codec settings with safe CPU codec settings."""
        patched = list(command)
        for index in range(len(patched) - 1):
            if patched[index] == "-c:v":
                patched[index + 1] = "libx264"
            if patched[index] == "-preset" and patched[index + 1] == "p5":
                patched[index + 1] = "slow"
        return patched

    def _gpu_used_label(self) -> str:
        """Describe GPU usage based on selected encoder."""
        codec = self._video_codec()
        if codec in {"h264_nvenc", "h264_videotoolbox", "h264_qsv", "h264_amf"}:
            return codec
        return "cpu"

    def _default_run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """Run command via subprocess and capture output."""
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def _resolve_color_values(self, profile: RenderProfile) -> ColorPresetValues:
        """Resolve color values from configured preset with explicit profile override."""
        return resolve_color_preset(
            settings=self._settings,
            raw_config=self._raw_config,
            preset_name=profile.color_preset,
        )


def _safe_float(value: Any, fallback: float) -> float:
    """Convert arbitrary value to float safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _fraction_to_float(raw: str) -> float:
    """Convert ffprobe fraction strings to float."""
    if "/" not in raw:
        return _safe_float(raw, 0.0)
    left, right = raw.split("/", 1)
    numerator = _safe_float(left, 0.0)
    denominator = _safe_float(right, 1.0)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _read_rotation(tags: dict[str, Any], side_data: list[Any]) -> int:
    """Extract integer rotation degrees from ffprobe tags/side-data."""
    rotate_raw = tags.get("rotate")
    if rotate_raw is not None:
        try:
            return int(float(str(rotate_raw))) % 360
        except ValueError:
            pass

    for item in side_data:
        if not isinstance(item, dict):
            continue
        value = item.get("rotation")
        if value is None:
            continue
        try:
            return int(float(str(value))) % 360
        except ValueError:
            continue

    return 0


def _timeline_duration(clips: list[ClipSegment], transitions: list[TransitionChoice]) -> float:
    """Compute resulting timeline duration after transition overlaps."""
    if not clips:
        return 0.0
    total = sum(clip.duration for clip in clips)
    overlap = sum(item.duration for item in transitions)
    return max(0.1, total - overlap)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to inclusive range."""
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _ff_escape(value: str) -> str:
    """Escape filter-compatible text for ffmpeg expressions."""
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
