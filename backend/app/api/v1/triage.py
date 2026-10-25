"""Triage queue — objects to review, sorted by risk, with analyst disposition."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db import risk_repo
from app.db.audit_repo import record_action
from app.db.session import get_session

router = APIRouter()


class TriageItem(BaseModel):
    id: int
    target: str
    score: int
    threat_level: str
    recommendation: str
    disposition: str
    disposition_by: str | None = None


class Reach(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0


class ContentTriageItem(BaseModel):
    """One VIDEO/post to review — the unit the ТЗ asks to prioritise."""
    id: int
    content_id: str
    author: str
    source: str
    url: str
    score: int
    threat_level: str
    breakdown: list = []
    recommendation: str
    reach: Reach = Reach()
    priority: int = 0          # risk × reach — the triage sort key
    disposition: str
    disposition_by: str | None = None
    track: str = ""            # SafeNet track: lottery | casino | pyramid | ""
    lang: str = ""
    caption: str = ""          # original post / message text
    transcript: str = ""       # retained speech (Whisper) — what was said in the clip
    ocr_text: str = ""         # retained on-screen text
    tags: list = []            # visual object tags


class DispositionIn(BaseModel):
    disposition: str       # pending | escalated | dismissed | watching


def _to_item(r) -> TriageItem:
    return TriageItem(id=r.id, target=r.target, score=r.score, threat_level=r.threat_level,
                      recommendation=r.recommendation, disposition=r.disposition,
                      disposition_by=r.disposition_by)


def _to_content_item(r, content=None) -> ContentTriageItem:
    return ContentTriageItem(
        id=r.id, content_id=r.content_id, author=r.author, source=r.source, url=r.url,
        score=r.score, threat_level=r.threat_level, breakdown=r.breakdown or [],
        recommendation=r.recommendation,
        reach=Reach(views=r.views, likes=r.likes, comments=r.comments, shares=r.shares),
        priority=r.priority, disposition=r.disposition, disposition_by=r.disposition_by,
        track=r.track or "", lang=r.lang or "",
        caption=(content.caption or "") if content else "",
        transcript=(content.transcript or "") if content else "",
        ocr_text=(content.ocr_text or "") if content else "",
        tags=(content.tags or []) if content else [],
    )


@router.get("", response_model=list[TriageItem])
def list_triage(
    disposition: str | None = None,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> list[TriageItem]:
    return [_to_item(r) for r in risk_repo.list_for_triage(session, disposition)]


@router.post("/{assessment_id}/disposition", response_model=TriageItem)
def set_disposition(
    assessment_id: int,
    body: DispositionIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> TriageItem:
    try:
        row = risk_repo.set_disposition(session, assessment_id, body.disposition, principal.subject)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    record_action(session, principal.subject, "triage.disposition", f"{row.target}={body.disposition}")
    return _to_item(row)


@router.get("/content", response_model=list[ContentTriageItem])
def list_content_triage(
    disposition: str | None = None,
    track: str | None = None,
    level: str | None = None,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> list[ContentTriageItem]:
    """Materials to review, highest priority first; filter by track / level / disposition."""
    rows = risk_repo.list_content_for_triage(session, disposition, track=track, level=level)
    # Batch-load the retained text for these content_ids (avoid N+1).
    from app.db.models import Content
    ids = [r.content_id for r in rows]
    by_id = {c.id: c for c in session.query(Content).filter(Content.id.in_(ids)).all()} if ids else {}
    return [_to_content_item(r, by_id.get(r.content_id)) for r in rows]


@router.post("/content/{content_risk_id}/disposition", response_model=ContentTriageItem)
def set_content_disposition(
    content_risk_id: int,
    body: DispositionIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> ContentTriageItem:
    try:
        row = risk_repo.set_content_disposition(session, content_risk_id, body.disposition,
                                                principal.subject)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    record_action(session, principal.subject, "triage.content_disposition",
                  f"{row.content_id}={body.disposition}")
    from app.db.models import Content
    return _to_content_item(row, session.get(Content, row.content_id))
