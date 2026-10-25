# ADR-0001 — Qdrant as the Scam Fingerprint vector store

**Status:** Accepted · **Date:** 2026-06-22

## Context
The Scam Fingerprint requires storing **multiple embeddings per content item** (text, visual, audio, face) and searching them with metadata filtering, on-prem. The ТЗ did not specify a vector store.

## Decision
Use **Qdrant** (self-hosted) with **named vectors** — one collection, one point per content, four named vectors per point. Recall runs per modality, then `compare()` re-ranks candidates by folding in hard identifiers.

## Consequences
- ✅ Native multi-vector points map cleanly to a composite fingerprint.
- ✅ Payload filtering (lang, author, time) without a second system.
- ✅ Self-hostable, good ANN recall, simple ops.
- ➖ One more datastore to operate and back up.

## Alternatives considered
- **pgvector** — fewer moving parts (we already run Postgres) and fine at ≤10K/day, but multi-vector-per-item and high-recall ANN are awkward. Kept as a fallback if store consolidation becomes a priority.
- **Milvus** — more powerful but heavier ops than warranted at this scale.
