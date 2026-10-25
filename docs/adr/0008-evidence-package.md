# ADR-0008 — Evidence Package as a tamper-evident report

**Status:** Accepted · **Date:** 2026-06-23

## Context
For a government body, the question after an AI verdict is «дальше что». The AI output (risk score, narrative, network) only has value if it can be **presented as evidence**. We already keep the hard parts architecturally: SHA-256 + WORM + chain of custody are project invariants.

## Decision
Add an **Evidence Package Generator** (`evidence_package.py`) that binds the AI output to the chain of custody into «Аналитическая справка с цифровыми доказательствами»:
- explainable risk with **each factor linked to its `evidence_id`**,
- the evidence list (sha256 + WORM key + collected_at per artifact),
- the AI narrative,
- a **manifest SHA-256** over the whole package → the справка itself is tamper-evident,
- a Markdown rendering for export/print (`GET /investigations/{id}/evidence-package`, audited; dashboard «Сформировать справку»).

## Consequences
- ✅ Turns AI output into a defensible, presentable document — the «дальше что» for the buyer.
- ✅ Cheap: sits directly on existing invariants (SHA-256/WORM/explainable scoring).
- ➖ Legal admissibility ultimately depends on jurisdiction/process — the package supports it, doesn't guarantee it. A future step is an Ed25519 signature over the manifest.

## Alternatives considered
- **Export raw JSON only** — not human-presentable, no integrity guarantee on the report itself; rejected.
