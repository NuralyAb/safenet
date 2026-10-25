"""Scam Fingerprint Engine.

A fingerprint is COMPOSITE, not a single vector:
  - SOFT: multimodal embeddings (text / visual / audio) -> cosine similarity ("looks 94% alike")
  - HARD: exact identifiers (telegram handle, crypto wallet, phone, domain) -> certain links

Soft similarity alone produces false "94%" on generic luxury/stock footage.
Hard identifiers give certainty and catch a scheme scaling across fresh accounts.
The final match score blends both, with hard hits dominating.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Named-vector weights for the soft component (must sum to 1.0)
SOFT_WEIGHTS = {"text": 0.5, "visual": 0.3, "audio": 0.2}
# A single shared hard identifier is strong evidence of one scheme.
HARD_HIT_BOOST = 0.6


@dataclass
class Fingerprint:
    content_id: str
    author: str
    vectors: dict[str, list[float]] = field(default_factory=dict)   # text/visual/audio/face
    # hard identifiers extracted from the content
    telegram: list[str] = field(default_factory=list)
    wallets: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    def hard_identifiers(self) -> set[str]:
        return {
            *(f"tg:{h.lower()}" for h in self.telegram),
            *(f"wallet:{w.lower()}" for w in self.wallets),
            *(f"phone:{p}" for p in self.phones),
            *(f"domain:{d.lower()}" for d in self.domains),
        }


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class MatchResult:
    content_id: str             # the candidate content this result refers to
    author: str
    soft_similarity: float
    shared_identifiers: list[str]
    score: float                # final blended 0..1
    likely_same_scheme: bool


def compare(a: Fingerprint, b: Fingerprint) -> MatchResult:
    """Blend soft (multimodal cosine) with hard (shared identifiers). `b` is the candidate."""
    soft = sum(
        w * _cosine(a.vectors.get(name, []), b.vectors.get(name, []))
        for name, w in SOFT_WEIGHTS.items()
    )
    shared = sorted(a.hard_identifiers() & b.hard_identifiers())
    hard = min(1.0, HARD_HIT_BOOST * len(shared))
    score = min(1.0, soft + hard - soft * hard)   # probabilistic OR
    return MatchResult(
        content_id=b.content_id,
        author=b.author,
        soft_similarity=round(soft, 3),
        shared_identifiers=shared,
        score=round(score, 3),
        likely_same_scheme=score >= 0.85 or bool(shared),
    )


# --- Qdrant integration -------------------------------------------------------
# Two-stage retrieval:
#   1. SOFT recall — ANN search per named vector (text/visual/audio/face), union candidates
#   2. HARD re-rank — compare() folds in shared identifiers; certain links float to the top
import uuid

# Modalities we index as named vectors. `face` participates in recall but not in
# the soft scheme-similarity score (faces link people, not scheme structure).
RECALL_MODALITIES = ("text", "visual", "audio", "face")

NAMESPACE = uuid.UUID("a7f00000-0000-4000-8000-000000000001")


def _point_id(content_id: str) -> str:
    """Stable Qdrant point id derived from content_id (Qdrant needs int/UUID)."""
    return str(uuid.uuid5(NAMESPACE, content_id))


class FingerprintStore:
    COLLECTION = "fingerprints"

    def __init__(self, client):  # qdrant_client.QdrantClient
        self.client = client

    def init_collection(self) -> None:
        """Create the collection with one named vector per modality (idempotent)."""
        from qdrant_client.models import Distance, VectorParams
        from app.core.config import settings

        if self.client.collection_exists(self.COLLECTION):
            return
        dims = {
            "text": settings.dim_text,
            "visual": settings.dim_visual,
            "audio": settings.dim_audio,
            "face": settings.dim_face,
        }
        self.client.create_collection(
            collection_name=self.COLLECTION,
            vectors_config={
                name: VectorParams(size=dim, distance=Distance.COSINE)
                for name, dim in dims.items()
            },
        )

    def upsert(self, fp: Fingerprint) -> None:
        from qdrant_client.models import PointStruct

        vectors = {k: v for k, v in fp.vectors.items() if k in RECALL_MODALITIES and v}
        payload = {
            "content_id": fp.content_id,
            "author": fp.author,
            "telegram": fp.telegram,
            "wallets": fp.wallets,
            "phones": fp.phones,
            "domains": fp.domains,
        }
        self.client.upsert(
            collection_name=self.COLLECTION,
            points=[PointStruct(id=_point_id(fp.content_id), vector=vectors, payload=payload)],
        )

    def _to_fingerprint(self, record) -> Fingerprint:
        p = record.payload or {}
        vec = record.vector or {}
        return Fingerprint(
            content_id=p.get("content_id", ""),
            author=p.get("author", ""),
            vectors={k: list(v) for k, v in vec.items()} if isinstance(vec, dict) else {},
            telegram=p.get("telegram", []),
            wallets=p.get("wallets", []),
            phones=p.get("phones", []),
            domains=p.get("domains", []),
        )

    def scroll_all(self, limit: int = 10000) -> list[Fingerprint]:
        """Pull every fingerprint from the collection (for scheme clustering)."""
        records, _ = self.client.scroll(
            collection_name=self.COLLECTION, limit=limit,
            with_payload=True, with_vectors=True,
        )
        return [self._to_fingerprint(r) for r in records]

    def search_similar(self, fp: Fingerprint, limit: int = 25,
                       recall_per_modality: int = 50) -> list[MatchResult]:
        """ANN recall across modalities -> dedupe -> compare() re-rank by blended score."""
        self_id = _point_id(fp.content_id)
        candidate_ids: set = set()
        for name in RECALL_MODALITIES:
            query = fp.vectors.get(name)
            if not query:
                continue
            hits = self.client.query_points(
                collection_name=self.COLLECTION,
                query=query,
                using=name,
                limit=recall_per_modality,
                with_payload=False,
            ).points
            candidate_ids.update(h.id for h in hits if h.id != self_id)

        if not candidate_ids:
            return []

        records = self.client.retrieve(
            collection_name=self.COLLECTION,
            ids=list(candidate_ids),
            with_payload=True,
            with_vectors=True,
        )
        results = [compare(fp, self._to_fingerprint(r)) for r in records]
        results.sort(key=lambda m: m.score, reverse=True)
        return results[:limit]
