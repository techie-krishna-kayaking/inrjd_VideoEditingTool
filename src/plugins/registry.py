"""In-memory plugin registry for lifecycle extension points."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PluginRegistry:
    """Registry of plugin identifiers grouped by lifecycle stage."""

    pre_run: list[str] = field(default_factory=list)
    post_run: list[str] = field(default_factory=list)

    def register_pre_run(self, plugin_name: str) -> None:
        """Register a plugin for pre-run execution."""
        self.pre_run.append(plugin_name)

    def register_post_run(self, plugin_name: str) -> None:
        """Register a plugin for post-run execution."""
        self.post_run.append(plugin_name)
