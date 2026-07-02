"""Discovery and filtering helpers for review engine inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.review.metadata import estimate_quality_score, orientation_from_dimensions, read_media_dimensions
from src.review.models import ReviewFilterOptions, ReviewMediaItem


BUCKET_TYPES: dict[str, str] = {
    "shortform_pictures": "image",
    "shortform_videos": "video",
    "longform_pictures": "image",
    "longform_videos": "video",
}

SUPPORTED_BUCKETS = tuple(BUCKET_TYPES.keys())


def discover_event_names(input_root: Path, target_event: str | None, all_events: bool) -> list[str]:
    """Resolve event list from input root and CLI target options."""
    if target_event:
        return [target_event]

    if not input_root.exists():
        return []

    candidates = sorted(item.name for item in input_root.iterdir() if item.is_dir())
    if all_events:
        return candidates
    return candidates


def build_review_queue(
    input_root: Path,
    event_name: str,
    bucket_filter: str | None,
    filters: ReviewFilterOptions,
    low_quality_threshold: int,
) -> list[ReviewMediaItem]:
    """Build review queue for one event and apply requested filters."""
    event_root = input_root / event_name
    if not event_root.exists() or not event_root.is_dir():
        return []

    buckets = [bucket_filter] if bucket_filter else list(SUPPORTED_BUCKETS)
    queue: list[ReviewMediaItem] = []

    for bucket in buckets:
        if bucket not in BUCKET_TYPES:
            continue
        bucket_dir = event_root / bucket
        if not bucket_dir.exists() or not bucket_dir.is_dir():
            continue

        for file_path in sorted(item for item in bucket_dir.iterdir() if item.is_file()):
            media_type = BUCKET_TYPES[bucket]
            size_bytes = int(file_path.stat().st_size)

            queue.append(
                ReviewMediaItem(
                    event_name=event_name,
                    bucket=bucket,
                    path=file_path,
                    media_type=media_type,
                    orientation="unknown",
                    width=None,
                    height=None,
                    size_bytes=size_bytes,
                    quality_score=None,
                    duplicate_key=None,
                )
            )

    return _apply_filters(queue=queue, filters=filters, low_quality_threshold=low_quality_threshold)


def _apply_filters(
    queue: list[ReviewMediaItem],
    filters: ReviewFilterOptions,
    low_quality_threshold: int,
) -> list[ReviewMediaItem]:
    """Apply filter set to a queue."""
    filtered = queue

    needs_metadata = filters.portrait_images or filters.landscape_images or filters.low_quality
    if needs_metadata:
        filtered = [_with_metadata(item) for item in filtered]

    if filters.duplicates:
        filtered = [_with_duplicate_key(item) for item in filtered]

    if filters.portrait_images:
        filtered = [
            item
            for item in filtered
            if item.media_type == "image" and item.orientation == "portrait"
        ]

    if filters.landscape_images:
        filtered = [
            item
            for item in filtered
            if item.media_type == "image" and item.orientation == "landscape"
        ]

    if filters.videos:
        filtered = [item for item in filtered if item.media_type == "video"]

    if filters.low_quality:
        filtered = [item for item in filtered if item.quality_score < low_quality_threshold]

    if filters.duplicates:
        counts: dict[str, int] = {}
        for item in filtered:
            key = item.duplicate_key or ""
            counts[key] = counts.get(key, 0) + 1
        filtered = [item for item in filtered if counts.get(item.duplicate_key or "", 0) > 1]

    return filtered


def _with_metadata(item: ReviewMediaItem) -> ReviewMediaItem:
    """Return item with dimensions/orientation/quality populated."""
    if item.width is not None and item.height is not None and item.quality_score is not None:
        return item

    width, height = read_media_dimensions(item.path, item.media_type)
    orientation = orientation_from_dimensions(width=width, height=height)
    quality_score = estimate_quality_score(width=width, height=height, size_bytes=item.size_bytes)
    return ReviewMediaItem(
        event_name=item.event_name,
        bucket=item.bucket,
        path=item.path,
        media_type=item.media_type,
        orientation=orientation,
        width=width,
        height=height,
        size_bytes=item.size_bytes,
        quality_score=quality_score,
        duplicate_key=item.duplicate_key,
    )


def _with_duplicate_key(item: ReviewMediaItem) -> ReviewMediaItem:
    """Return item with duplicate key populated."""
    if item.duplicate_key is not None:
        return item

    duplicate_key = _duplicate_key(file_path=item.path, size_bytes=item.size_bytes)
    return ReviewMediaItem(
        event_name=item.event_name,
        bucket=item.bucket,
        path=item.path,
        media_type=item.media_type,
        orientation=item.orientation,
        width=item.width,
        height=item.height,
        size_bytes=item.size_bytes,
        quality_score=item.quality_score,
        duplicate_key=duplicate_key,
    )


def _duplicate_key(file_path: Path, size_bytes: int) -> str:
    """Build a lightweight duplicate key from size + sampled content hash."""
    digest = hashlib.sha1()
    digest.update(str(size_bytes).encode("utf-8"))

    if size_bytes == 0:
        return digest.hexdigest()

    with file_path.open("rb") as handle:
        first = handle.read(65536)
        digest.update(first)
        if size_bytes > 65536:
            seek_position = max(0, size_bytes - 65536)
            handle.seek(seek_position)
            tail = handle.read(65536)
            digest.update(tail)

    return digest.hexdigest()
