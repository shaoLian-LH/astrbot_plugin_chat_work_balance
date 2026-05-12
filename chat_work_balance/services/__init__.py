from __future__ import annotations


class ResourceAnalysisService:
    """Slice A only assembles dependencies; runtime behavior lands in Slice B."""

    def __init__(self, context, plugin_config) -> None:
        self._context = context
        self._plugin_config = plugin_config


class MergedForwardReader:
    """Slice A only assembles dependencies; runtime behavior lands in Slice B."""

    pass


__all__ = ["MergedForwardReader", "ResourceAnalysisService"]
