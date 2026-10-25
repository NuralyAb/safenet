# ADR-0003 — Deterministic, explainable risk score

**Status:** Accepted · **Date:** 2026-06-22

## Context
The risk score drives escalation to manual review and may end up in legal proceedings. "The AI decided 92/100" is not defensible. The ТЗ already specifies a transparent weighted factor table.

## Decision
**AI extracts facts and evidence; a deterministic engine computes the score.** Each of the six ТЗ factors gets a `[0,1]` strength plus `evidence_ids` pointing to originals in the WORM bucket. The engine returns the score, a `LOW/MEDIUM/HIGH/CRITICAL` level, and a per-factor breakdown. **The LLM never assigns the number.** Implemented in `backend/app/services/risk_engine.py`.

## Consequences
- ✅ Every point is traceable to a specific piece of evidence — defensible in review/court.
- ✅ Reproducible and unit-testable (`tests/test_risk_engine.py`).
- ✅ Weights are tunable policy, visible and versionable.
- ➖ Less "magic" than an end-to-end learned scorer — intentional; explainability wins here.

## Alternatives considered
- **LLM/ML end-to-end scorer** — higher ceiling, but opaque and indefensible for this use case. May inform factor *strengths*, never the final score.
