# ADR-0009 — Per-video risk scoring (content as the primary unit)

**Status:** Accepted · **Date:** 2026-06-23

## Context
The ТЗ («AI Media Watch») asks the system to «формировать риск-оценку **контента**» — score and prioritise individual videos. The original implementation scored only the **account**: `RiskAssessment` is keyed by target, `risk_signals()` OR-aggregates claim flags across all of a target's content, and a score is produced only when an analyst opens an investigation (Temporal). The continuous-collection stream never scored what it ingested. Two ТЗ patterns — «агрессивные инвестиционные призывы» and «скрытые способы вовлечения аудитории» — were not modelled.

## Decision
Introduce a **two-tier deterministic score**, reusing the same engine ([ADR-0003](0003-explainable-deterministic-risk-score.md)):

- **Tier 1 — content risk (new, primary).** Every collected video is scored automatically in the Celery pipeline (`process → fingerprint → score_content`) and persisted to the `content_risk` table. `evidence_id` traces to that content's own evidence. Implemented in `services/content_scoring.py` + `services/investigation.py::content_risk_signals`.
- **Tier 2 — account roll-up (existing).** The account-level `RiskAssessment` / Investigator flow is unchanged.

**The six ТЗ factors and their weights are NOT changed.** The two new patterns are modelled as **intensifiers of the parent factor's strength**, not as new factors:

| Pattern | Parent factor | Strength |
|---|---|---|
| обещание дохода | `financial_promises` | 0.6 |
| + агрессивный призыв | `financial_promises` | 1.0 |
| реферальная схема | `referral_structure` | 0.6 |
| + скрытое вовлечение | `referral_structure` | 1.0 |

This also replaces the previous binary `1.0/0.0` strengths on the per-video path with a graded scale, so the score discriminates weak from blatant violations. Multi-frame video analysis (config `video_frames`) feeds vision/OCR across the whole clip, not just the frame at 1.0s.

## Consequences
- ✅ Direct fit to the ТЗ: a risk score + explanation per video, prioritised in the «Материалы» queue (`GET /triage/content`).
- ✅ The continuous-collection stream now scores everything it ingests, automatically.
- ✅ `evidence_id` is populated per content — every per-video point is traceable.
- ✅ Invariants preserved: AI only extracts facts, `assess()` stays deterministic, the ТЗ weight table is untouched.
- ➖ Two scoring entry points (pipeline + account roll-up) must keep using the one engine — enforced by both delegating to `risk_engine.assess`.
- ➖ `content_id` on `content_risk` is a plain indexed string (no hard FK), like `RiskAssessment.target`, so scoring works even before a `Content` row is persisted.

## Alternatives considered
- **Add a 7th/8th risk factor** for the two new patterns — rejected: would break the ТЗ-fixed weight contract (ADR-0003). Modelling them as strength intensifiers keeps the contract intact.
- **Score only on analyst investigation (status quo)** — rejected: leaves the continuous stream unscored, contradicting the ТЗ's «на постоянной основе».
