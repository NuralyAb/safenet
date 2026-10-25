"""Per-content risk scoring (a video / post / screenshot / chat message).

The unit here is ONE piece of content — what SafeNet KZ asks to score and explain.
Scoring is the SafeNet deterministic per-track engine (safenet/scoring.py): the AI
only supplies signals with quotes, the engine computes the number and the level.
"""
from __future__ import annotations

import math

from app.services import risk_engine

# Reach metric keys (audience «охват») captured at collection time.
REACH_KEYS = ("views", "likes", "comments", "shares")


def normalize_reach(raw: dict | None) -> dict:
    """Coerce a platform's metrics into the canonical reach dict (ints, >= 0)."""
    raw = raw or {}
    out = {}
    for k in REACH_KEYS:
        try:
            out[k] = max(0, int(raw.get(k) or 0))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def reach_score(views: int) -> float:
    """Normalize reach to [0,1] on a log scale: ~0 at 1 view, 1.0 at ≥10M views."""
    if not views or views < 0:
        return 0.0
    return min(1.0, math.log10(views + 1) / 7.0)   # 10^7 = 10M -> 1.0


def priority_from(score: int, views: int = 0) -> int:
    """Review-queue ranking = risk amplified by reach (0..200).

    A high-risk post seen by thousands outranks the same risk seen by nobody. The
    risk SCORE itself is untouched; priority only orders the queue.
    """
    return int(round(max(0, score) * (1.0 + reach_score(views))))


def score_content(facts: dict | None = None, *, text: str | None = None, safenet: dict | None = None,
                  segments: list[tuple[str, str]] | None = None, scheme_matches: int = 0,
                  related_objects: int = 0, evidence_ids: list[str] | None = None,
                  has_license: bool | None = None, llm=None) -> risk_engine.RiskAssessment:
    """Deterministic, explainable score for one piece of content.

    Signal source, most precise first:
      * `safenet`  — a detection already computed by the pipeline (serialised dict)
      * `segments` / `text` — run the SafeNet detector now
      * `facts`    — legacy boolean flags only (no text available) -> weak signals
    `scheme_matches` / `related_objects` add the «повторяемость и связи» factor.
    """
    from app.services.safenet import detect, facts_to_hits, score_detection
    from app.services.safenet.detector import Detection

    if safenet:
        detection = Detection.from_dict(safenet)
    elif segments or text:
        detection = detect(segments or [("text", text or "")], llm=llm)
    else:
        detection = Detection(hits=facts_to_hits(facts or {}), language="", identifiers={}, text="")
    licensed = bool((facts or {}).get("has_license")) if has_license is None else bool(has_license)
    return score_detection(detection, has_license=licensed, scheme_matches=scheme_matches,
                           related_objects=related_objects, evidence_ids=evidence_ids)
