from dataclasses import dataclass

import pytest

import app.workers.collectors  # noqa: F401 — registers adapters
from app.services.ssrf import UnsafeURLError
from app.workers.collectors.base import BaseCollector, CollectedItem
from app.workers.collectors.platforms import YouTubeCollector
from app.workers.collectors.registry import available_sources, get_collector
from app.workers.collectors.runner import collect_via


# --- registry ----------------------------------------------------------------
def test_registry_resolves_known_sources():
    assert isinstance(get_collector("youtube"), YouTubeCollector)
    assert {"youtube", "tiktok", "instagram", "telegram", "whatsapp"} <= set(available_sources())


def test_unknown_source_raises():
    with pytest.raises(ValueError):
        get_collector("myspace")


def test_whatsapp_is_registered_but_unsupported():
    wa = get_collector("whatsapp")
    assert wa.health() is False
    with pytest.raises(NotImplementedError, match="end-to-end encrypted"):
        wa.fetch("anyone")


# --- runner (fakes, no network) ----------------------------------------------
@dataclass
class _Ref:
    sha256: str
    raw_key: str
    evidence_key: str
    size: int
    content_type: str


class FakeEvidenceStore:
    def __init__(self):
        self.stored = []

    def store(self, data, source, content_type="", ext=""):
        self.stored.append((source, len(data)))
        digest = "d" * 64
        key = f"{source}/{digest}.{ext}"
        return _Ref(sha256=digest, raw_key=key, evidence_key=key,
                    size=len(data), content_type=content_type)


class FakeCollector(BaseCollector):
    source = "youtube"

    def __init__(self, items):
        self._items = items

    def fetch(self, target, *, limit=20):
        return self._items

    def health(self):
        return True


def _item(url):
    return CollectedItem(source="youtube", external_id="v1", author="@scam", url=url,
                         media=b"\x00\x01\x02", content_type="video/mp4", ext="mp4",
                         text="invest now", wallets=["0x" + "a" * 40])


def test_collect_via_stores_evidence_and_emits_contract():
    store = FakeEvidenceStore()
    out = collect_via(FakeCollector([_item("https://www.youtube.com/watch?v=1")]),
                      store, "@scam", allowed_hosts=["www.youtube.com"])
    assert len(out) == 1
    row = out[0]
    assert row["content_id"] == row["sha256"] == "d" * 64       # content-addressed
    assert row["raw_key"].startswith("youtube/")
    assert row["wallets"] == ["0x" + "a" * 40]
    assert store.stored == [("youtube", 3)]                     # original was stored


def test_collect_via_blocks_ssrf_url():
    store = FakeEvidenceStore()
    with pytest.raises(UnsafeURLError):
        collect_via(FakeCollector([_item("http://169.254.169.254/meta")]),
                    store, "@scam", allowed_hosts=["www.youtube.com"])
