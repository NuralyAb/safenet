import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AuditLogEntry,
    Base,
    Content,
    Evidence,
    RiskAssessment,
    User,
)
from app.services.audit import AuditEntry, make_entry, verify_chain


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_user_crud(session):
    session.add(User(username="analyst-1", role="analyst",
                     password_hash="$argon2id$...", totp_secret="JBSWY3DPEHPK3PXP"))
    session.commit()
    u = session.query(User).filter_by(username="analyst-1").one()
    assert u.role == "analyst" and u.id is not None


def test_content_evidence_relationship(session):
    c = Content(id="c1", source="youtube", external_id="yt-1", author="@scam",
                url="https://www.youtube.com/watch?v=1", sha256="a" * 64)
    c.evidence.append(Evidence(sha256="a" * 64, evidence_key="youtube/aa/aa/" + "a" * 64,
                               size=1024, content_type="video/mp4"))
    session.add(c)
    session.commit()
    got = session.get(Content, "c1")
    assert len(got.evidence) == 1
    assert got.evidence[0].evidence_key.startswith("youtube/")


def test_risk_assessment_json_breakdown(session):
    session.add(RiskAssessment(
        target="@money_fast", score=84, threat_level="HIGH",
        breakdown=[{"factor": "financial_promises", "contribution": 25, "evidence_ids": ["ev-1"]}],
        recommendation="escalate",
    ))
    session.commit()
    r = session.query(RiskAssessment).one()
    assert r.score == 84
    assert r.breakdown[0]["evidence_ids"] == ["ev-1"]   # JSON round-trips


def test_audit_rows_persist_and_chain_verifies(session):
    # Persist a real hash chain, read it back, and verify integrity end-to-end.
    e0 = make_entry(None, "2026-06-22T10:00:00Z", "analyst-1", "login", "-")
    e1 = make_entry(e0, "2026-06-22T10:01:00Z", "analyst-1", "investigation.open", "@x")
    for e in (e0, e1):
        session.add(AuditLogEntry(seq=e.seq, ts=e.ts, actor=e.actor, action=e.action,
                                  target=e.target, prev_hash=e.prev_hash, entry_hash=e.entry_hash))
    session.commit()

    rows = session.query(AuditLogEntry).order_by(AuditLogEntry.seq).all()
    rebuilt = [AuditEntry(r.seq, r.ts, r.actor, r.action, r.target, r.prev_hash, r.entry_hash)
               for r in rows]
    assert verify_chain(rebuilt) is True
