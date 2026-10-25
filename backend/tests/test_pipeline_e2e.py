"""End-to-end: collect -> process -> fingerprint.

The default test composes the three stage cores with fakes and asserts the dict
contracts line up at every boundary — this catches contract drift across stages
in CI, without any live service. The integration test exercises real Qdrant.
"""
from dataclasses import dataclass

import pytest

from app.services.pipeline import extract_features, fingerprint_from_processed
from app.workers.collectors.base import BaseCollector, CollectedItem
from app.workers.collectors.runner import collect_via

# Stage contracts (mirror of tasks.py; tasks.py imports celery so we don't import it here).
_COLLECT_OUT = {"content_id", "source", "sha256", "raw_key", "author"}
_PROCESS_OUT = {"content_id", "sha256", "features"}


@dataclass
class _Ref:
    sha256: str
    raw_key: str
    evidence_key: str
    size: int
    content_type: str


class FakeEvidence:
    def store(self, data, source, content_type="", ext=""):
        digest = "e" * 64
        key = f"{source}/{digest}"
        return _Ref(sha256=digest, raw_key=key, evidence_key=key,
                    size=len(data), content_type=content_type)


class FakeCollector(BaseCollector):
    source = "youtube"

    def fetch(self, target, *, limit=20):
        return [CollectedItem(
            source="youtube", external_id="v1", author="@scam",
            url="https://www.youtube.com/watch?v=1", media=b"\x00\x01",
            content_type="video/mp4", ext="mp4", text="invest 100 get 1000",
            wallets=["USDT-X"], telegram=["fastmoney"],
        )]

    def health(self):
        return True


class FakeEmbedder:
    def embed_text(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_stage_contracts_compose_end_to_end():
    # 1) collect
    collected = collect_via(FakeCollector(), FakeEvidence(), "@scam",
                            allowed_hosts=["www.youtube.com"])
    assert len(collected) == 1
    assert _COLLECT_OUT <= collected[0].keys()

    # 2) process — collect output must satisfy what process consumes & produce _PROCESS_OUT
    processed = extract_features(FakeEmbedder(), collected[0])
    assert _PROCESS_OUT <= processed.keys()
    assert processed["features"]["text"] == [1.0, 0.0, 0.0]

    # 3) fingerprint — identifiers + id survive end to end
    fp = fingerprint_from_processed(processed)
    assert fp.content_id == collected[0]["content_id"]
    assert "wallet:usdt-x" in fp.hard_identifiers()
    assert "tg:fastmoney" in fp.hard_identifiers()


@pytest.mark.integration
def test_full_chain_against_live_qdrant():
    from app.services.fingerprint import Fingerprint, FingerprintStore
    from app.db.clients import qdrant_client

    store = FingerprintStore(qdrant_client())
    store.init_collection()
    a = Fingerprint("e2e-a", "@a", {"text": [1.0, 0.0]}, wallets=["E2E-W"])
    b = Fingerprint("e2e-b", "@b", {"text": [1.0, 0.0]}, wallets=["E2E-W"])
    store.upsert(a)
    store.upsert(b)
    matches = store.search_similar(a)
    assert any(m.content_id == "e2e-b" for m in matches)
