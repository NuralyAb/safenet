"""«Мониторинг схем»: the monitor finds schemes by itself, only while it is switched on."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AppSetting, Base, Content, ContentRisk, MonitorEvent, MonitorSource
from app.services.safenet import monitor


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[t.__table__ for t in
                                             (AppSetting, Content, ContentRisk, MonitorEvent, MonitorSource)])
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _no_telegram(*_a, **_k):
    raise AssertionError("demo sources must not touch the network")


def test_monitor_is_off_by_default(session):
    assert monitor.is_enabled(session) is False
    monitor.set_enabled(session, True, now=100.0)
    assert monitor.is_enabled(session) and monitor.started_at(session) == 100.0
    monitor.set_enabled(session, False)
    assert monitor.is_enabled(session) is False


def test_demo_stream_is_deterministic_and_mixes_tracks():
    mix = {"lottery": 0.5, "none": 0.5}
    assert monitor.demo_post("instagram", "giv_shymkent", mix, 3) == monitor.demo_post("instagram", "giv_shymkent", mix, 3)
    texts = {monitor.demo_post("instagram", "giv_shymkent", mix, n)["text"] for n in range(30)}
    assert len(texts) > 20                                   # a stream, not one repeated post


def test_tick_finds_schemes_and_queues_them(session):
    assert monitor.seed_demo_sources(session) == len(monitor.DEMO_SOURCES)
    assert monitor.seed_demo_sources(session) == 0           # idempotent
    t = 1_000.0
    total = {"scanned": 0, "flagged": 0}
    for i in range(40):                                      # ~40 rounds of every demo source
        out = monitor.tick(session, now=t + i * 10, telegram_fetch=_no_telegram)
        total["scanned"] += out["scanned"]
        total["flagged"] += out["flagged"]
    assert total["scanned"] >= 300
    assert 0 < total["flagged"] < total["scanned"]          # finds AND clean posts
    found = {e.track for e in session.query(MonitorEvent).filter_by(flagged=True)}
    assert found == {"lottery", "casino", "pyramid"}
    clean = session.query(MonitorEvent).filter_by(author="shymkent_news", flagged=True).count()
    assert clean == 0                                        # news / shop sources stay clean
    queued = session.query(ContentRisk).count()
    assert 0 < queued <= total["flagged"]                    # finds are in the review queue
    ev = session.query(MonitorEvent).filter_by(flagged=True).first()
    assert ev.signals and ev.breakdown and ev.content_id
    assert session.get(Content, ev.content_id).caption == ev.text


def test_sources_are_polled_on_their_interval(session):
    monitor.seed_demo_sources(session)
    first = monitor.tick(session, now=5_000.0, telegram_fetch=_no_telegram)
    assert first["polled"] == len(monitor.DEMO_SOURCES)
    assert monitor.tick(session, now=5_001.0, telegram_fetch=_no_telegram)["polled"] == 0


def test_telegram_posts_are_checked_once(session):
    src = monitor.add_telegram_channel(session, "https://t.me/s/Test_Channel/12", "analyst")
    assert (src.handle, src.connector) == ("Test_Channel", "telegram_web")
    posts = [{"id": "Test_Channel/1", "url": "https://t.me/Test_Channel/1", "views": 900,
              "text": "Розыгрыш iPhone! Номер = 1000 тг, оплата на Kaspi, крутим рандомайзер в эфире"},
             {"id": "Test_Channel/2", "url": "https://t.me/Test_Channel/2", "views": 300,
              "text": "Сегодня в Шымкенте солнечно, +24"}]
    fetch = lambda handle, limit=20: posts                    # noqa: E731
    assert monitor.tick(session, now=10.0, telegram_fetch=fetch)["scanned"] == 2
    again = monitor.tick(session, now=10.0 + monitor.TELEGRAM_INTERVAL, telegram_fetch=fetch)
    assert again["polled"] == 1 and again["scanned"] == 0     # same posts are not re-checked
    hit = session.query(MonitorEvent).filter_by(external_id="Test_Channel/1").one()
    assert hit.flagged and hit.track == "lottery"


def test_broken_source_does_not_stop_the_monitor(session):
    monitor.add_telegram_channel(session, "@broken_channel", "analyst")
    monitor.seed_demo_sources(session)

    def boom(*_a, **_k):
        raise RuntimeError("t.me unreachable")
    out = monitor.tick(session, now=50.0, telegram_fetch=boom)
    assert out["scanned"] == len(monitor.DEMO_SOURCES)
    assert "unreachable" in session.query(MonitorSource).filter_by(handle="broken_channel").one().last_error


def test_bad_channel_names_are_rejected(session):
    with pytest.raises(ValueError):
        monitor.add_telegram_channel(session, "@a!", "analyst")


def test_feed_and_status(session):
    monitor.seed_demo_sources(session)
    monitor.set_enabled(session, True, now=900.0)
    for i in range(20):
        monitor.tick(session, now=1_000.0 + i * 10, telegram_fetch=_no_telegram)
    feed = monitor.feed(session)
    assert feed and all(e["flagged"] for e in feed)
    assert feed[0]["id"] > feed[-1]["id"]                    # newest first
    assert monitor.feed(session, after=feed[0]["id"]) == []
    st = monitor.status(session, now=1_200.0)
    assert st["enabled"] and st["scanned"] >= st["flagged"] > 0
    assert sum(v["high"] + v["medium"] for v in st["by_track"].values()) == st["flagged"]
    assert len(st["timeline"]) == monitor.TIMELINE_MINUTES
    assert st["active_sources"] == len(monitor.DEMO_SOURCES)


def test_feed_retention(session, monkeypatch):
    monkeypatch.setattr(monitor, "KEEP_EVENTS", 15)
    monitor.seed_demo_sources(session)
    for i in range(5):
        monitor.tick(session, now=2_000.0 + i * 10, telegram_fetch=_no_telegram)
    assert session.query(MonitorEvent).count() <= 15


def test_feed_since_start_hides_previous_runs(session):
    monitor.seed_demo_sources(session)
    for i in range(10):
        monitor.tick(session, now=3_000.0 + i * 10, telegram_fetch=_no_telegram)
    assert monitor.feed(session)
    assert monitor.feed(session, since=4_000.0) == []         # a new run starts with an empty feed
