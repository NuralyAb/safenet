import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.audit_repo import SqlAuditRepo, record_action
from app.db.models import AuditLogEntry, Base
from app.services.audit import AuditEntry, verify_chain


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_record_action_persists_a_verifiable_chain(session):
    record_action(session, "analyst-1", "investigation.open", "@money_fast", ts="2026-06-22T10:00:00Z")
    record_action(session, "analyst-1", "graph.view", "@money_fast", ts="2026-06-22T10:01:00Z")
    record_action(session, "supervisor-2", "biometric.view", "person:1", ts="2026-06-22T10:02:00Z")

    rows = session.query(AuditLogEntry).order_by(AuditLogEntry.seq).all()
    assert [r.seq for r in rows] == [0, 1, 2]
    rebuilt = [AuditEntry(r.seq, r.ts, r.actor, r.action, r.target, r.prev_hash, r.entry_hash)
               for r in rows]
    assert verify_chain(rebuilt) is True


def test_chain_continues_across_repo_instances(session):
    record_action(session, "a", "login", "-", ts="t0")
    # a fresh repo must pick up the existing tail and keep the chain going
    repo = SqlAuditRepo(session)
    assert repo.last_entry().seq == 0
    record_action(session, "a", "investigation.open", "@x", ts="t1")
    rows = session.query(AuditLogEntry).order_by(AuditLogEntry.seq).all()
    assert rows[1].prev_hash == rows[0].entry_hash       # linkage intact


def test_tamper_is_detectable_after_persist(session):
    record_action(session, "a", "login", "-", ts="t0")
    record_action(session, "a", "biometric.view", "p1", ts="t1")
    rows = session.query(AuditLogEntry).order_by(AuditLogEntry.seq).all()
    rebuilt = [AuditEntry(r.seq, r.ts, r.actor, r.action, r.target, r.prev_hash, r.entry_hash)
               for r in rows]
    rebuilt[1].__dict__["action"] = "login"             # simulate edited history
    assert verify_chain(rebuilt) is False
