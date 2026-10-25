"""Startup initialization — make the datastores ready, idempotently.

Creates (if absent): MinIO raw + WORM buckets, the Qdrant fingerprint collection
(named vectors), and the Neo4j constraints. Each underlying call is idempotent,
so repeated boots are safe.

`initialize_stores` takes already-built service objects so it is trivial to test
with mocks; `run_startup` wires the real clients.
"""
from __future__ import annotations

import logging

log = logging.getLogger("afm.startup")


def initialize_stores(evidence_store, fingerprint_store, graph_builder) -> None:
    evidence_store.ensure_buckets()
    fingerprint_store.init_collection()
    graph_builder.init_schema()
    log.info("startup: MinIO buckets, Qdrant collection, Neo4j schema ready")


def run_startup() -> None:
    from app.core.config import settings
    from app.db.clients import minio_client, neo4j_driver, qdrant_client
    from app.services.evidence import EvidenceStore
    from app.services.fingerprint import FingerprintStore
    from app.services.graph_builder import GraphBuilder

    initialize_stores(
        EvidenceStore(minio_client(), settings.minio_raw_bucket, settings.minio_evidence_bucket),
        FingerprintStore(qdrant_client()),
        GraphBuilder(neo4j_driver()),
    )
