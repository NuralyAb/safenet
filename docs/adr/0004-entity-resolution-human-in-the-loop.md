# ADR-0004 — Human-in-the-loop entity resolution

**Status:** Accepted · **Date:** 2026-06-22

## Context
"Same Person Detection" is the riskiest claim in the ТЗ. Face/voice match plus contact overlap gives a *candidate*, not a fact. Auto-asserting identity in a law-enforcement system is legally and technically indefensible and risks false accusations.

## Decision
Entity resolution produces a **`LinkCandidate`** with a confidence score (weighted over face/voice/contact/behavioral signals) and the evidence behind it. A **`SAME_PERSON` edge enters the Fraud Graph only after an analyst confirms it** (`confirmed_by` recorded). The invariant `AUTO_CONFIRM_FORBIDDEN = True` is enforced in `backend/app/services/entity_resolution.py`. Unconfirmed candidates render as dashed `SAME_PERSON?` edges in the graph.

## Consequences
- ✅ No machine-asserted identities; analyst accountability is recorded.
- ✅ Confidence + evidence make confirmation fast without hiding uncertainty.
- ➖ Requires analyst review throughput — accepted; identity claims must not scale unattended.

## Alternatives considered
- **Auto-link above a confidence threshold** — rejected; a single false high-confidence match could misidentify a person. Unacceptable for this domain.
