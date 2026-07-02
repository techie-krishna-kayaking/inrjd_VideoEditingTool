# Changelog

All notable changes to this project are documented here.

## [0.2.0] - 2026-07-02

### Added
- Unified source-video rendering engine for short and long workflows.
- Automatic clip usage memory at output/reports/clip_usage.json.
- Media usage database at output/reports/media_usage.json.
- Render history database at output/reports/render_history.json.
- Multi-format reporting (JSON, CSV, TXT) for video renders.
- Retry-once error recovery and failed job descriptors in output/failed/.
- Color preset system (natural, temple, festival, cinematic, warm, cool).
- Transition probability controls and additional transition styles.
- CLI commands: render-short-videos and render-long-videos.

### Improved
- Logger formatting now includes elapsed execution time and module context.
- FFmpeg execution path with GPU-first strategy and CPU fallback.
- Audio mixing chain with fade, crossfade, loudness normalization, and ducking.
- Long-video thumbnail pipeline for source videos.

### Fixed
- Removed dead branch in organizer workflow event filtering.
- Reduced duplicate logic by centralizing reporting helpers.
