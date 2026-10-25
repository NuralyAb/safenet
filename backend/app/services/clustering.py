"""Scam scheme clustering — group fingerprints that are the same operation.

Union-find over pairwise fingerprint matches: any two that share a hard identifier
or are soft-similar above threshold join the same cluster. A cluster = one
ScamSchema scaling across multiple accounts/posts.

Pure (operates on Fingerprint objects) -> unit-tested without Qdrant. The live
version pulls all fingerprints from Qdrant and writes clusters back as ScamSchema
nodes (integration).
"""
from __future__ import annotations

import hashlib

from app.services.fingerprint import compare

DEFAULT_THRESHOLD = 0.85


class _DSU:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_fingerprints(fingerprints, threshold: float = DEFAULT_THRESHOLD) -> list[list[str]]:
    """Return clusters of content_ids, largest first. Singletons included."""
    ids = [f.content_id for f in fingerprints]
    dsu = _DSU(ids)
    for i in range(len(fingerprints)):
        for j in range(i + 1, len(fingerprints)):
            m = compare(fingerprints[i], fingerprints[j])
            if m.likely_same_scheme or m.score >= threshold:
                dsu.union(fingerprints[i].content_id, fingerprints[j].content_id)

    groups: dict[str, list[str]] = {}
    for cid in ids:
        groups.setdefault(dsu.find(cid), []).append(cid)
    return sorted((sorted(g) for g in groups.values()), key=len, reverse=True)


def scam_schema_id(members: list[str]) -> str:
    """Stable id for a scheme cluster (order-independent)."""
    digest = hashlib.sha1(",".join(sorted(members)).encode()).hexdigest()
    return f"schema-{digest[:12]}"


def schema_assignments(clusters: list[list[str]], min_size: int = 2) -> list[dict]:
    """Keep real schemes (>=min_size); a single post is not a 'scheme'."""
    out = [
        {"schema_id": scam_schema_id(c), "members": sorted(c), "size": len(c)}
        for c in clusters if len(c) >= min_size
    ]
    return sorted(out, key=lambda s: s["size"], reverse=True)


def rebuild_scam_schemas(store, graph, threshold: float = DEFAULT_THRESHOLD,
                         min_size: int = 2) -> list[dict]:
    """Pull all fingerprints from Qdrant, cluster them, write ScamSchema nodes to Neo4j."""
    fingerprints = store.scroll_all()
    clusters = cluster_fingerprints(fingerprints, threshold)
    assignments = schema_assignments(clusters, min_size)
    graph.write_scam_schemas(assignments)
    return assignments
