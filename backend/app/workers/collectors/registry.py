"""Collector registry — resolve a source name to its adapter.

Adapters self-register via @register("youtube"). Unknown/unsupported sources
raise so the pipeline fails loudly rather than silently skipping a target.
"""
from __future__ import annotations

from app.workers.collectors.base import BaseCollector

_REGISTRY: dict[str, type[BaseCollector]] = {}


def register(source: str):
    def _wrap(cls: type[BaseCollector]):
        cls.source = source
        _REGISTRY[source] = cls
        return cls
    return _wrap


def get_collector(source: str) -> BaseCollector:
    if source not in _REGISTRY:
        raise ValueError(
            f"No collector for source {source!r}. Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[source]()


def available_sources() -> list[str]:
    return sorted(_REGISTRY)
