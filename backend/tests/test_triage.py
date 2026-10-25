import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import risk_repo
from app.db.models import Base
from app.main import app


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed(session):
    risk_repo.upsert_assessment(session, "@a", 40, "MEDIUM", [], "r")
    risk_repo.upsert_assessment(session, "@b", 84, "HIGH", [], "r")
    risk_repo.upsert_assessment(session, "@c", 20, "LOW", [], "r")


def test_triage_sorted_by_risk_desc(session):
    _seed(session)
    rows = risk_repo.list_for_triage(session)
    assert [r.target for r in rows] == ["@b", "@a", "@c"]   # highest risk first
    assert rows[0].disposition == "pending"


def test_upsert_is_one_row_per_target_and_keeps_disposition(session):
    a = risk_repo.upsert_assessment(session, "@a", 40, "MEDIUM", [], "r")
    risk_repo.set_disposition(session, a.id, "escalated", "analyst-1")
    # re-investigation updates the score but must NOT wipe the analyst decision
    risk_repo.upsert_assessment(session, "@a", 90, "HIGH", [], "r2")
    rows = risk_repo.list_for_triage(session)
    assert len(rows) == 1
    assert rows[0].score == 90 and rows[0].disposition == "escalated"


def test_set_disposition_records_analyst_and_filters(session):
    _seed(session)
    b = [r for r in risk_repo.list_for_triage(session) if r.target == "@b"][0]
    risk_repo.set_disposition(session, b.id, "dismissed", "analyst-1")
    dismissed = risk_repo.list_for_triage(session, disposition="dismissed")
    assert [r.target for r in dismissed] == ["@b"]
    assert dismissed[0].disposition_by == "analyst-1"


def test_invalid_disposition_rejected(session):
    a = risk_repo.upsert_assessment(session, "@a", 40, "MEDIUM", [], "r")
    with pytest.raises(ValueError):
        risk_repo.set_disposition(session, a.id, "bogus", "x")


def test_triage_endpoint_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/triage").status_code == 401
