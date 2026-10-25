# ADR-0002 — Temporal for the AI Investigator

**Status:** Accepted · **Date:** 2026-06-22

## Context
The AI Investigator is a multi-step process (collect → match → graph → score → report). In a law-enforcement context it must be **reproducible and auditable** — we need to show exactly what data each step used and reproduce the result. The high-throughput content pipeline runs on Celery, but that does not give durable, replayable execution.

## Decision
Run the content pipeline on **Celery** (simple, sufficient at ≤10K/day) and run the **AI Investigator as a Temporal workflow**. Temporal records every step + result; replay is deterministic and folds into the evidence chain. The deterministic risk score is computed inside an activity; the LLM only writes the narrative.

## Consequences
- ✅ Durable, replayable, auditable investigations out of the box.
- ✅ Built-in retries/timeouts per activity for flaky collection/inference.
- ➖ Two execution systems (Celery + Temporal). Accepted: each is used where it fits, and Temporal's value is concentrated exactly on the auditable path.

## Alternatives considered
- **Celery canvas everywhere** — no durable replay; reconstructing an investigation for evidence would be manual and fragile.
- **LangGraph** — good agent ergonomics but weaker durability/audit guarantees than Temporal.
