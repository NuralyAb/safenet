"""Pluggable collector interface (one adapter per source).

Adapters fetch raw items; the runner (collectors/runner.py) hashes them, stores
originals to the WORM evidence bucket, applies the SSRF guard, and emits the
pipeline contract. Keeping fetch and storage separate means every source gets
chain-of-custody for free and the fragile per-source code stays isolated.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class CollectedItem:
    source: str                 # "youtube" | "telegram" | "tiktok" | "instagram"
    external_id: str
    author: str
    url: str
    media: bytes                # the downloaded original (video/audio)
    content_type: str = "application/octet-stream"
    ext: str = ""
    text: str = ""              # caption / description / subtitles
    # hard identifiers extracted from text/metadata
    telegram: list[str] = field(default_factory=list)
    wallets: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    # optional pre-extracted modalities (else the pipeline extracts later)
    audio: bytes | None = None
    image: bytes | None = None
    # audience reach («охват»): {views, likes, comments, shares} — drives triage priority
    reach: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class BaseCollector(abc.ABC):
    source: str

    @abc.abstractmethod
    def fetch(self, target: str, *, limit: int = 20) -> list[CollectedItem]:
        """Fetch recent content for a target account/channel."""

    def search(self, query: str, *, limit: int = 20) -> list[CollectedItem]:
        """Discover NEW content by keyword/hashtag. Override where supported."""
        raise NotImplementedError(f"{self.source}: keyword discovery not supported")

    @abc.abstractmethod
    def health(self) -> bool:
        """False if the adapter is currently broken (rate-limited / DOM change / no creds)."""
