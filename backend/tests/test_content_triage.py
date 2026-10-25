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


def test_content_triage_sorted_by_risk_desc(session):
    risk_repo.upsert_content_risk(session, "v1", 80, "HIGH", [], "r",
                                  author="@a", source="youtube", url="u1")
    risk_repo.upsert_content_risk(session, "v2", 30, "LOW", [], "r")
    risk_repo.upsert_content_risk(session, "v3", 55, "MEDIUM", [], "r")
    rows = risk_repo.list_content_for_triage(session)
    assert [r.content_id for r in rows] == ["v1", "v3", "v2"]   # highest risk first
    assert rows[0].disposition == "pending"
    assert rows[0].source == "youtube"


def test_reach_drives_priority_ordering(session):
    # higher raw risk but seen by nobody -> priority == risk == 84
    risk_repo.upsert_content_risk(session, "niche", 84, "HIGH", [], "r", reach={"views": 0})
    # lower risk but viral -> 50 × (1 + 1.0) = 100, outranks the niche clip
    risk_repo.upsert_content_risk(session, "viral", 50, "MEDIUM", [], "r",
                                  reach={"views": 10_000_000})
    rows = risk_repo.list_content_for_triage(session)
    assert [r.content_id for r in rows] == ["viral", "niche"]   # risk × reach, not raw risk
    assert rows[0].views == 10_000_000 and rows[0].priority == 100
    assert rows[1].priority == 84


def test_content_upsert_is_one_row_and_keeps_disposition(session):
    r = risk_repo.upsert_content_risk(session, "v1", 30, "LOW", [], "r")
    risk_repo.set_content_disposition(session, r.id, "escalated", "analyst-1")
    # re-scoring updates the number but must NOT wipe the analyst decision
    risk_repo.upsert_content_risk(session, "v1", 90, "HIGH", [], "r2")
    rows = risk_repo.list_content_for_triage(session)
    assert len(rows) == 1
    assert rows[0].score == 90 and rows[0].disposition == "escalated"


def test_content_disposition_filters_and_records_analyst(session):
    risk_repo.upsert_content_risk(session, "v1", 80, "HIGH", [], "r")
    v1 = risk_repo.list_content_for_triage(session)[0]
    risk_repo.set_content_disposition(session, v1.id, "dismissed", "analyst-2")
    dismissed = risk_repo.list_content_for_triage(session, disposition="dismissed")
    assert [r.content_id for r in dismissed] == ["v1"]
    assert dismissed[0].disposition_by == "analyst-2"


def test_invalid_content_disposition_rejected(session):
    r = risk_repo.upsert_content_risk(session, "v1", 10, "LOW", [], "r")
    with pytest.raises(ValueError):
        risk_repo.set_content_disposition(session, r.id, "bogus", "x")


def test_content_triage_endpoint_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/triage/content").status_code == 401
