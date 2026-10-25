"""Persistence for risk assessments — feeds the triage queue.

One row per object (upsert by target). The analyst disposition survives
re-investigation (a re-run updates the score, not the human decision).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ContentRisk, RiskAssessment

DISPOSITIONS = {"pending", "escalated", "dismissed", "watching"}


def upsert_assessment(session: Session, target: str, score: int, threat_level: str,
                      breakdown: list, recommendation: str) -> RiskAssessment:
    row = session.query(RiskAssessment).filter_by(target=target).one_or_none()
    if row is None:
        row = RiskAssessment(target=target, score=score, threat_level=threat_level,
                             breakdown=breakdown, recommendation=recommendation)
        session.add(row)
    else:
        row.score = score
        row.threat_level = threat_level
        row.breakdown = breakdown
        row.recommendation = recommendation   # disposition kept as-is
    session.commit()
    return row


def list_for_triage(session: Session, disposition: str | None = None) -> list[RiskAssessment]:
    q = session.query(RiskAssessment)
    if disposition is not None:
        q = q.filter_by(disposition=disposition)
    return q.order_by(RiskAssessment.score.desc()).all()


def set_disposition(session: Session, assessment_id: int, disposition: str, by: str) -> RiskAssessment | None:
    if disposition not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {sorted(DISPOSITIONS)}")
    row = session.get(RiskAssessment, assessment_id)
    if row is None:
        return None
    row.disposition = disposition
    row.disposition_by = by
    session.commit()
    return row


# --- per-video (content) risk: feeds the "materials" triage queue -------------
def upsert_content_risk(session: Session, content_id: str, score: int, threat_level: str,
                        breakdown: list, recommendation: str, *,
                        author: str = "", source: str = "", url: str = "",
                        reach: dict | None = None, track: str | None = None,
                        lang: str | None = None) -> ContentRisk:
    """One row per content (upsert by content_id). Analyst disposition is preserved
    across re-scoring (a re-run updates the score, not the human decision).

    Reach («охват») is stored and folded into `priority` (= risk × reach) — the
    triage sort key. The risk score itself stays untouched (ТЗ weights intact)."""
    from app.services.content_scoring import normalize_reach, priority_from

    r = normalize_reach(reach)
    priority = priority_from(score, r["views"])
    row = session.query(ContentRisk).filter_by(content_id=content_id).one_or_none()
    if row is None:
        row = ContentRisk(content_id=content_id, author=author, source=source, url=url,
                          score=score, threat_level=threat_level, breakdown=breakdown,
                          recommendation=recommendation, priority=priority,
                          track=track or "", lang=lang or "", **r)
        session.add(row)
    else:
        row.score = score
        row.threat_level = threat_level
        row.breakdown = breakdown
        row.recommendation = recommendation
        row.priority = priority
        if track is not None:
            row.track = track
        if lang is not None:
            row.lang = lang
        for k, v in r.items():
            setattr(row, k, v)
        if author:
            row.author = author
        if source:
            row.source = source
        if url:
            row.url = url
    session.commit()
    return row


def list_content_for_triage(session: Session, disposition: str | None = None, *,
                            track: str | None = None, level: str | None = None) -> list[ContentRisk]:
    # Prioritise by reach-weighted priority, then raw risk — «приоритизация материалов».
    q = session.query(ContentRisk)
    if disposition is not None:
        q = q.filter_by(disposition=disposition)
    if track:
        q = q.filter_by(track=track)
    if level:
        q = q.filter_by(threat_level=level)
    return q.order_by(ContentRisk.priority.desc(), ContentRisk.score.desc()).all()


def set_content_disposition(session: Session, content_risk_id: int, disposition: str,
                            by: str) -> ContentRisk | None:
    if disposition not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {sorted(DISPOSITIONS)}")
    row = session.get(ContentRisk, content_risk_id)
    if row is None:
        return None
    row.disposition = disposition
    row.disposition_by = by
    session.commit()
    return row
