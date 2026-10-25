from fastapi.testclient import TestClient

from app.main import app
from app.services import agent, hunter


def test_generate_queries_mock_uses_seed(monkeypatch):
    import app.services.runtime_config as rc
    monkeypatch.setattr(rc, "get_value", lambda k: "mock")
    qs = hunter.generate_queries(4)
    assert len(qs) == 4 and all(isinstance(q, str) and q for q in qs)
    assert qs == hunter._SEED_QUERIES[:4]                 # deterministic in mock


def test_agent_routes_hunt_intent():
    assert agent._choose_mock("запусти охоту")["tool"] == "hunt"
    assert agent._choose_mock("поищи схемы")["tool"] == "hunt"
    assert agent._choose_mock("как считается риск")["tool"] != "hunt"


def test_adapt_mock_builds_queries_from_patterns():
    qs = hunter._adapt_mock({"casino", "ставки"}, {"betbot"}, {"scam.io"}, 6)
    assert any("betbot" in q for q in qs)             # learned from a found telegram channel
    assert any("scam.io" in q for q in qs)            # and a found domain
    assert any("без лицензии" in q for q in qs)       # and a gambling tag


def test_adapt_queries_safe_without_data():
    assert hunter.adapt_queries(None, 5) == hunter._SEED_QUERIES[:5]   # no rows -> seed fallback


def test_hunt_synthetic_creates_scored_findings():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db.models import Base, ContentRisk

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        created = hunter._hunt_synthetic(s, ["youtube", "tiktok"], ["инвест казино"], 3)
        assert created == 6                               # 2 sources × 3 clips, inline, no network
        rows = s.query(ContentRisk).all()
        assert len(rows) == 6
        assert all(r.author.startswith("@") for r in rows)   # plausible handles, not the query
        assert any(r.score >= 50 for r in rows)              # real deterministic risk


def test_hunt_endpoint_requires_auth():
    assert TestClient(app).post("/api/v1/hunt", json={"count": 6}).status_code == 401
