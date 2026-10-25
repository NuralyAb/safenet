# SafeNet KZ — Architecture

AI Platform for Fraud Intelligence & Social Media Investigation.

**Deployment profile:** production-grade · on-prem / self-hosted · internal gov/law-enforcement tool · ≤10K videos/day · biometrics permitted by mandate · audit + chain of custody required.

---

## 1. Guiding principles

| Principle | Consequence in the design |
|-----------|---------------------------|
| **Explainable, not black-box** | AI extracts facts → a *deterministic* engine computes the risk score → every point traces to an `evidence_id`. The LLM never assigns the number. |
| **Chain of custody** | Originals stored to a WORM bucket with SHA-256 at collection time, so evidence survives post deletion. |
| **Human-in-the-loop on identity** | `SAME_PERSON` is a *candidate* with confidence until an analyst confirms it. Never machine-asserted. |
| **On-prem in production** | Self-hosted LLM (vLLM), embeddings, biometrics. **Prototype exception:** external AI (OpenAI/Anthropic) behind a swappable provider abstraction (`app/services/ai/`), synthetic data only — see ADR-0005. |
| **Complexity spent on integrity, not throughput** | At ≤10K/day no Kafka/streaming is needed; the budget goes to auditability and defensibility. |

---

## 2. Component overview

```
Sources (YouTube/TikTok/Instagram via yt-dlp · Telegram via Telethon · WhatsApp = impossible)
        │
        ▼
collector-worker (Celery, egress) ── SSRF guard ──►  MinIO RAW + WORM (SHA-256 at collect)
        │
        ▼
processing-worker (Celery, NO egress — internal net)
  ffmpeg (audio + multi-frame) → Whisper STT · vision tags + OCR across frames · NLP content facts
                              → face/voice biometrics (self-hosted)   [all via AI provider abstraction]
        │
        ▼
Fraud Intelligence Engine
  Scam Fingerprint (Qdrant: upsert/search/cluster→ScamSchema)
  Per-video Risk Engine (deterministic, explainable → content_risk)   ← scored automatically in-pipeline
  Fraud Graph (Neo4j+GDS: communities/centrality)
  Money Flow (on-chain → exchange boundary)  ·  Biometric ER (Same-Person, human-in-the-loop)
        │
        ▼
AI Investigator (Temporal: collect→match→network→score→narrate)      ← account-level roll-up
        │
        ▼
Dashboard (React + TanStack Query + Cytoscape): Материалы (per-video triage), investigation+report,
          evidence package, fraud graph + GDS insights, money flow
```

**AI provider abstraction** (`app/services/ai/`): `Embedder/Transcriber/ChatLLM/VisionTagger/FaceEmbedder/SpeakerEmbedder` Protocols → OpenAI/Anthropic (prototype) or local (production), selected by `AI_PROVIDER`. The pipeline depends only on the interfaces.

---

## 3. Data stores & ownership

| Store | Owns | Notes |
|-------|------|-------|
| **PostgreSQL** | metadata, extracted claims, risk assessments, **audit_log** | source of truth for relational + audit |
| **Qdrant** | Scam Fingerprint vectors | named vectors per modality (text/visual/audio/face) |
| **Neo4j (+GDS)** | Fraud Graph | community detection + centrality = network analysis |
| **MinIO** | raw media + **WORM evidence** | object-lock bucket = chain of custody |
| **Redis** | Celery broker + cache | |
| **Temporal** | Investigator workflow state | durable, replayable = auditable |

---

## 4. Killer features — implementation

### Scam Fingerprint (`backend/app/services/fingerprint.py`)
Composite fingerprint = **SOFT** (multimodal cosine over named vectors) **+ HARD** (shared Telegram/wallet/phone/domain). Retrieval is two-stage: ANN recall per modality in Qdrant → dedupe → `compare()` re-rank that folds in hard identifiers. Hard hits dominate, so a scheme scaling across fresh accounts via a shared wallet is caught with certainty, not a fuzzy "94%".

### Fraud Graph (`backend/app/services/graph_builder.py`)
Typed nodes/edges with provenance (`confidence`, `source`, `evidence_id`). GDS Louvain → "organized network of N objects"; betweenness centrality → ringleader / shared-wallet choke points.

### AI Investigator (`backend/app/workflows/`)
Durable Temporal workflow: `collect_profile → match_fingerprints → build_network → compute_risk → compose_narrative`. The score is computed by the deterministic Risk Engine inside an activity; the LLM only writes the narrative from established facts. Temporal's replay log feeds the evidence chain.

### Scheme clustering (`backend/app/services/clustering.py`)
Union-find over pairwise fingerprint matches → `ScamSchema` clusters; `rebuild_scam_schemas` pulls all fingerprints from Qdrant and writes `ScamSchema` nodes + `MATCHES_SCHEMA` edges to Neo4j (`POST /graph/schemas/rebuild`).

### Money Flow (`backend/app/services/money_flow.py` + `chain.py`)
Public on-chain bridge `account → wallet → exchange` with an **explicit boundary**: wallet → bank account is the agency's data, not ours. A complement, not a rival. See ADR-0007.

### Biometric ER / Same-Person (`backend/app/services/biometrics.py`)
Face/voice identity embeddings → cosine signals → a `SAME_PERSON` **candidate**; never auto-confirmed. Recognition embeddings are self-hosted-only (no external API does face/voice ID). See ADR-0006.

### Evidence Package (`backend/app/services/evidence_package.py`)
Binds the AI output to the chain of custody → a tamper-evident «Аналитическая справка» (manifest SHA-256 + Markdown). See ADR-0008.

---

## 5. Risk scoring (`backend/app/services/risk_engine.py`)

Weights from the ТЗ (sum = 100): financial_promises 25 · referral_structure 20 · known_scheme_repetition 20 · suspicious_links 15 · gambling_content 10 · infra_anonymity 10. Factor strengths come from real signals — **NLP content facts** (`claims.py`, LLM→booleans), scheme-match count, network size, vision tags across frames. The LLM produces facts, never the number; the engine returns a traceable breakdown + `LOW/MEDIUM/HIGH/CRITICAL`.

**Two tiers (one engine).** The ТЗ asks for a risk score *per content*, so the unit of scoring is the video:

- **Per-video (`content_scoring.py` → `content_risk` table)** — every collected video is scored automatically in the pipeline (`process → fingerprint → score_content`), prioritised in the «Материалы» queue (`GET /triage/content`), with `evidence_id` tracing to that content. Strengths are **graded** (not binary): the two ТЗ patterns «агрессивные инвестиционные призывы» and «скрытые способы вовлечения» are modelled as *intensifiers* that lift the parent factor's strength `0.6 → 1.0`, so the weight table stays fixed (see ADR-0009).
- **Per-account (Investigator)** — the account-level roll-up over a target's content; feeds the account triage queue.

Multi-frame analysis (`media.py`, config `VIDEO_FRAMES`) samples several frames across each clip so a marker shown anywhere — not just at 1.0s — is caught by vision/OCR.

---

## 6. Security & compliance (implemented)

- **Auth**: argon2id passwords, TOTP MFA, short-lived JWT + refresh, server-side RBAC (`core/security.py`, `ratelimit.py`).
- **Tamper-evident audit**: hash-chained, persisted to an append-only `audit_log` table (DB trigger blocks UPDATE/DELETE) — `services/audit.py`, `db/audit_repo.py`.
- **Chain of custody**: SHA-256 at collect → MinIO WORM (object-lock).
- **At rest**: AES-256-GCM for biometric embeddings (`crypto.py`); fail-closed config rejects default secrets in production.
- **Network**: `processing-worker` isolated (no internet egress); SSRF allowlist on collector URLs (`ssrf.py`); non-root containers.
- See [docs/security/threat-model.md](docs/security/threat-model.md) and [security-audit.md](docs/security/security-audit.md).

---

## 7. Delivery status (see [docs/PROTOTYPE_ROADMAP.md](docs/PROTOTYPE_ROADMAP.md))

Phases A–E + extra features **complete**: infra, auth/RBAC/refresh, DB models+migrations, collectors, evidence WORM, multimodal (ffmpeg multi-frame→Whisper/vision/OCR/NLP), embeddings+fingerprint+clustering, per-video risk + «Материалы» triage, Fraud Graph+GDS, Temporal Investigator, dashboard, Money Flow, Evidence Package, biometric ER. **179 backend + 6 frontend tests** green. 🟡 not yet run against live services (integration markers + real key smoke pending). Remaining: live run, GPU for biometrics/local provider, minor UI/KMS/TLS polish.

---

## 8. Decision records

See [docs/adr/](docs/adr/):
- [ADR-0001](docs/adr/0001-vector-store-qdrant.md) — Qdrant for the Scam Fingerprint store
- [ADR-0002](docs/adr/0002-investigator-on-temporal.md) — Temporal for the AI Investigator
- [ADR-0003](docs/adr/0003-explainable-deterministic-risk-score.md) — deterministic, explainable risk score
- [ADR-0004](docs/adr/0004-entity-resolution-human-in-the-loop.md) — human-in-the-loop entity resolution
- [ADR-0005](docs/adr/0005-external-ai-provider-abstraction.md) — external AI via swappable provider abstraction (prototype)
- [ADR-0006](docs/adr/0006-biometrics-self-hosted-only.md) — biometric recognition is self-hosted-only
- [ADR-0007](docs/adr/0007-money-flow-exchange-boundary.md) — Money Flow stops at the exchange boundary
- [ADR-0008](docs/adr/0008-evidence-package.md) — Evidence Package as tamper-evident report
- [ADR-0009](docs/adr/0009-per-video-risk-scoring.md) — per-video risk scoring (content as the primary unit)
