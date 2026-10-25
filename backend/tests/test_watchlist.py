import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.main import app
from app.services import watchlist
from app.workers.collectors.platforms import youtube_search_expr


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_add_list_and_deactivate(session):
    watchlist.add_target(session, "youtube", "account", "@scam", "analyst-1")
    watchlist.add_target(session, "youtube", "keyword", "инвест казино", "analyst-1")
    active = watchlist.list_active(session)
    assert {t.kind for t in active} == {"account", "keyword"}

    watchlist.deactivate(session, active[0].id)
    assert len(watchlist.list_active(session)) == 1          # one deactivated
    assert len(watchlist.list_all(session)) == 2             # but still listed


def test_adding_existing_reactivates_not_duplicates(session):
    t1 = watchlist.add_target(session, "youtube", "account", "@scam", "a")
    watchlist.deactivate(session, t1.id)
    t2 = watchlist.add_target(session, "youtube", "account", "@scam", "a")   # same -> reactivate
    assert t2.id == t1.id and t2.active is True
    assert len(watchlist.list_all(session)) == 1


def test_invalid_kind_rejected(session):
    with pytest.raises(ValueError):
        watchlist.add_target(session, "youtube", "bogus", "x", "a")


def test_mark_run_sets_timestamp(session):
    t = watchlist.add_target(session, "youtube", "account", "@scam", "a")
    watchlist.mark_run(session, t.id, "2026-06-23T10:00:00Z")
    assert session.get(type(t), t.id).last_run_at == "2026-06-23T10:00:00Z"


def test_per_target_schedule_add_update_and_clear(session):
    # one Instagram once a day, another twice a day — independent cadences
    daily = watchlist.add_target(session, "instagram", "account", "@a", "u", interval_seconds=86400)
    twice = watchlist.add_target(session, "instagram", "account", "@b", "u", interval_seconds=43200,
                                 video_limit=3)
    assert daily.interval_seconds == 86400
    assert twice.interval_seconds == 43200 and twice.video_limit == 3

    # edit cadence, then reset it back to the global default
    watchlist.update_target(session, daily.id, interval_seconds=3600)
    assert session.get(type(daily), daily.id).interval_seconds == 3600
    watchlist.update_target(session, daily.id, clear_interval=True)
    assert session.get(type(daily), daily.id).interval_seconds is None


def test_schedule_validation_rejects_bad_values(session):
    with pytest.raises(ValueError):
        watchlist.add_target(session, "youtube", "account", "@x", "u", interval_seconds=10)  # < 60
    with pytest.raises(ValueError):
        watchlist.add_target(session, "youtube", "account", "@y", "u", video_limit=0)         # < 1


def test_discovery_search_expression_is_proactive():
    # keyword discovery finds NEW objects (not only known handles)
    assert youtube_search_expr("онлайн казино без лицензии", 15) == "ytsearch15:онлайн казино без лицензии"


def test_watchlist_endpoint_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/watchlist").status_code == 401
