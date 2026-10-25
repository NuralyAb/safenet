import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import notifications_repo as notif
from app.db.models import Base
from app.services import watchlist


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_records_only_for_watched_accounts(session):
    watchlist.add_target(session, "youtube", "account", "@watched", "a")
    # watched -> recorded
    row = notif.record_new_video(session, content_id="c1", author="@watched",
                                 source="youtube", url="u", score=70, threat_level="HIGH")
    assert row is not None
    # unwatched -> skipped
    assert notif.record_new_video(session, content_id="c2", author="@stranger") is None
    assert notif.unread_count(session) == 1


def test_idempotent_per_content(session):
    watchlist.add_target(session, "youtube", "account", "@watched", "a")
    notif.record_new_video(session, content_id="c1", author="@watched")
    notif.record_new_video(session, content_id="c1", author="@watched")   # same content
    assert notif.unread_count(session) == 1


def test_match_is_case_insensitive(session):
    watchlist.add_target(session, "youtube", "account", "@Watched", "a")
    assert notif.record_new_video(session, content_id="c1", author="@watched") is not None


def test_match_ignores_at_prefix_mismatch(session):
    # watch target entered WITH @, yt-dlp stores author WITHOUT @ — must still match
    watchlist.add_target(session, "youtube", "account", "@amidom4ru", "a")
    assert notif.record_new_video(session, content_id="c1", author="amidom4ru") is not None


def test_keyword_target_does_not_notify(session):
    watchlist.add_target(session, "youtube", "keyword", "инвест казино", "a")
    assert notif.record_new_video(session, content_id="c1", author="инвест казино") is None


def test_maybe_alert_fires_on_high_risk_even_if_unwatched(session):
    # no watch target — but high score crosses the threshold → radar alert
    row = notif.maybe_alert(session, content_id="c1", author="@stranger", score=80,
                            threat_level="HIGH", min_score=65)
    assert row is not None and row.reason == "high_risk"


def test_maybe_alert_skips_below_threshold_when_unwatched(session):
    assert notif.maybe_alert(session, content_id="c1", author="@stranger", score=40,
                             threat_level="MEDIUM", min_score=65) is None


def test_maybe_alert_watched_takes_priority_reason(session):
    watchlist.add_target(session, "youtube", "account", "@watched", "a")
    row = notif.maybe_alert(session, content_id="c1", author="@watched", score=10,
                            threat_level="LOW", min_score=65)
    assert row is not None and row.reason == "watched"


def test_mark_read_and_mark_all(session):
    watchlist.add_target(session, "youtube", "account", "@watched", "a")
    r1 = notif.record_new_video(session, content_id="c1", author="@watched")
    notif.record_new_video(session, content_id="c2", author="@watched")
    notif.mark_read(session, r1.id)
    assert notif.unread_count(session) == 1
    assert notif.mark_all_read(session) == 1
    assert notif.unread_count(session) == 0
    # already-read is not re-counted
    assert notif.mark_all_read(session) == 0
