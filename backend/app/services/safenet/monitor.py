"""SafeNet scheme monitor — finds paid giveaways, hidden casino ads and pyramids by itself.

The analyst starts and stops it with one button («Мониторинг схем»). While it is on, a
loop in the collector worker (tasks.collect_safenet_monitor) calls `tick` every couple
of seconds: each due source is polled, every NEW post is checked by the same
deterministic engine as «Проверка контента», and every check is written to the live
feed (monitor_event). Posts with score ≥ 40 also enter the review queue (content_risk)
and the graph, so they show up in «Материалы», campaigns and dossiers.

Connectors:
  telegram_web — public Telegram channels via the t.me/s/<channel> web preview (no login)
  demo         — the built-in synthetic demo sources: a deterministic stream of synthetic
                 posts from the labelled dev/test/holdout pools (never real accounts)

WhatsApp has no public feed (end-to-end encryption), so it is not monitored; exported
group chats are checked on «Проверка контента → Группа / чат».
"""
from __future__ import annotations

import hashlib
import random
import time
from functools import lru_cache

from app.services.safenet import analyze_segments
from app.services.safenet.demo import DEMO_URL
from app.services.safenet.scoring import FLAG_THRESHOLD

ENABLED_KEY = "safenet_monitor_enabled"
STARTED_KEY = "safenet_monitor_started_at"
PLATFORMS = ("telegram", "instagram", "tiktok", "youtube")
TELEGRAM_INTERVAL = 300          # seconds between polls of a real public channel
KEEP_EVENTS = 5000               # live-feed retention (the review queue keeps the finds)
TIMELINE_MINUTES = 15

# (platform, handle, title, track mix, seconds between posts) — synthetic demo sources;
# handles match the demo network so finds join the same graph, campaigns and dossiers.
DEMO_SOURCES: list[tuple[str, str, str, dict[str, float], int]] = [
    ("telegram", "kz_bet_signals", "KZ Bet Signals", {"casino": 0.6, "none": 0.4}, 6),
    ("instagram", "giv_shymkent", "Гив Шымкент", {"lottery": 0.55, "none": 0.45}, 7),
    ("telegram", "bereke_invest", "BEREKE INVEST | Закрытый клуб", {"pyramid": 0.6, "none": 0.4}, 7),
    ("tiktok", "streamer_azamat", "streamer_azamat", {"casino": 0.5, "none": 0.5}, 8),
    ("instagram", "qazaq_utys_kz", "Qazaq Ұтыс", {"lottery": 0.45, "casino": 0.1, "none": 0.45}, 8),
    ("instagram", "aru_profit", "aru_profit", {"pyramid": 0.45, "none": 0.55}, 9),
    ("telegram", "shymkent_baraholka", "Барахолка Шымкент", {"lottery": 0.12, "pyramid": 0.06, "none": 0.82}, 5),
    ("telegram", "shymkent_news", "Шымкент Новости", {"none": 1.0}, 6),
    ("instagram", "arzan_shop", "Арзан", {"none": 1.0}, 7),
    ("youtube", "sport_kz", "sport_kz", {"casino": 0.12, "none": 0.88}, 9),
]
_VIEWS = {"telegram": (800, 60_000), "instagram": (1_500, 120_000), "tiktok": (5_000, 900_000),
          "youtube": (300, 80_000)}


# ---- settings ------------------------------------------------------------------
def is_enabled(session) -> bool:
    from app.db import settings_repo as cfg
    return cfg.get_bool(session, ENABLED_KEY, False)


def set_enabled(session, on: bool, now: float | None = None) -> None:
    from app.db import settings_repo as cfg
    cfg.set(session, ENABLED_KEY, "true" if on else "false")
    if on:
        cfg.set(session, STARTED_KEY, f"{now or time.time():.3f}")
    session.commit()


def started_at(session) -> float:
    from app.db import settings_repo as cfg
    try:
        return float(cfg.get(session, STARTED_KEY) or 0)
    except ValueError:
        return 0.0


# ---- sources -------------------------------------------------------------------
def seed_demo_sources(session) -> int:
    """Create the synthetic demo sources once (idempotent)."""
    from app.db.models import MonitorSource

    have = {(s.platform, s.handle) for s in session.query(MonitorSource).filter_by(connector="demo")}
    n = 0
    for platform, handle, title, _mix, every in DEMO_SOURCES:
        if (platform, handle) not in have:
            session.add(MonitorSource(platform=platform, handle=handle, title=title, connector="demo",
                                      interval_seconds=every, added_by="demo"))
            n += 1
    session.commit()
    return n


def add_telegram_channel(session, target: str, added_by: str):
    """Add a public Telegram channel (real connector). Returns the source row."""
    from app.db.models import MonitorSource
    from app.services.telegram_web import normalize_channel

    handle = normalize_channel(target)
    if not handle or not handle.replace("_", "").isalnum() or len(handle) < 4:
        raise ValueError("Нужен публичный Telegram-канал: @name или t.me/name")
    row = session.query(MonitorSource).filter_by(platform="telegram", handle=handle).one_or_none()
    if row is None:
        row = MonitorSource(platform="telegram", handle=handle, title=f"@{handle}", connector="telegram_web",
                            interval_seconds=TELEGRAM_INTERVAL, added_by=added_by)
        session.add(row)
    row.active = True
    session.commit()
    return row


# ---- connectors ------------------------------------------------------------------
@lru_cache(maxsize=1)
def _pools() -> dict[str, list[dict]]:
    from app.services.safenet.evaluation import load

    rows = [r for name in ("dev", "test", "holdout") for r in load(name)]
    pools: dict[str, list[dict]] = {"none": [r for r in rows if r["label"] == 0]}
    for track in ("lottery", "casino", "pyramid"):
        pools[track] = [r for r in rows if r["label"] == 1 and r.get("track") == track]
    return pools


_TAILS = ["", " 🔥", " 🙂", " !!", " #Шымкент", " #Алматы", " 💯"]


def demo_post(platform: str, handle: str, mix: dict[str, float], n: int) -> dict:
    """The n-th synthetic post of a demo source (deterministic)."""
    rng = random.Random(f"{platform}|{handle}|{n}")
    track = rng.choices(list(mix), weights=list(mix.values()))[0]
    row = rng.choice(_pools()[track])
    lo, hi = _VIEWS.get(platform, (500, 50_000))
    return {"id": f"{handle}-{n}", "url": f"{DEMO_URL}{platform}/{handle}/{n}",
            "text": row["text"] + rng.choice(_TAILS), "views": rng.randrange(lo, hi)}


def _fetch(src, telegram_fetch) -> list[dict]:
    if src.connector == "demo":
        mix = next((m for p, h, _t, m, _e in DEMO_SOURCES if (p, h) == (src.platform, src.handle)), {"none": 1.0})
        post = demo_post(src.platform, src.handle, mix, src.cursor)
        src.cursor += 1
        return [post]
    if src.connector == "telegram_web":
        return telegram_fetch(src.handle, limit=20)
    return []


# ---- checking --------------------------------------------------------------------
def _signals(breakdown: list[dict]) -> list[dict]:
    out = []
    for b in breakdown:
        if b.get("kind") != "signal" or b.get("contribution", 0) <= 0:
            continue
        q = next((q["text"] for q in b.get("quotes") or [] if q.get("text") and not q["text"].startswith("(")), "")
        out.append({"label": b.get("label") or b["factor"], "quote": q[:80], "contribution": b["contribution"]})
    out.sort(key=lambda s: -s["contribution"])
    return out[:4]


def _to_queue(session, src, post: dict, a, det, graph) -> str:
    """Put a flagged post into the review queue (+ graph). Same text from the same source = one row."""
    from app.db.models import Content, ContentRisk
    from app.services.content_scoring import normalize_reach, priority_from

    cid = hashlib.sha256(f"monitor|{src.platform}|{src.handle}|{post['text']}".encode("utf-8")).hexdigest()
    reach = normalize_reach({"views": post.get("views") or 0})
    risk = session.query(ContentRisk).filter_by(content_id=cid).one_or_none()
    if risk is None:
        session.add(ContentRisk(content_id=cid, author=src.handle, source=src.platform, url=post.get("url", ""),
                                score=a.score, threat_level=a.threat_level.value, breakdown=a.breakdown,
                                recommendation=a.recommendation, track=a.track, lang=a.language,
                                priority=priority_from(a.score, reach["views"]), **reach))
    if session.get(Content, cid) is None:
        session.add(Content(id=cid, external_id=str(post["id"])[:128], sha256=cid, source=src.platform,
                            author=src.handle, url=post.get("url", ""), lang=a.language or "ru",
                            caption=post["text"]))
    if graph is not None:
        ids = det.identifiers
        try:
            graph.link_identifiers(src.handle, telegram=ids.get("telegram", []), domains=ids.get("domains", []),
                                   phones=ids.get("phones", []), cards=ids.get("cards", []),
                                   promo_codes=ids.get("promo_codes", []),
                                   short_links=ids.get("short_links", []), source="monitor")
        except Exception:  # noqa: BLE001 — graph is best-effort
            pass
    return cid


def check_post(session, src, post: dict, now: float, graph=None):
    """Check one post and record it in the feed. Returns the event, or None if already seen."""
    from app.db.models import MonitorEvent

    ext = str(post["id"])[:128]
    if session.query(MonitorEvent.id).filter_by(source_id=src.id, external_id=ext).first():
        return None
    text = (post.get("text") or "").strip()
    a, det = analyze_segments([("caption", text)]) if text else (None, None)
    score = a.score if a else 0
    flagged = bool(a and score >= FLAG_THRESHOLD)
    ev = MonitorEvent(source_id=src.id, external_id=ext, platform=src.platform, author=src.handle,
                      url=post.get("url", ""), text=text[:2000], views=int(post.get("views") or 0), score=score,
                      threat_level=a.threat_level.value if a else "LOW", track=(a.track if flagged else ""),
                      lang=(a.language if a else "") or "", flagged=flagged,
                      signals=_signals(a.breakdown) if a else [], breakdown=a.breakdown if flagged else [],
                      created_ts=now)
    if flagged:
        ev.content_id = _to_queue(session, src, post, a, det, graph)
    session.add(ev)
    src.scanned += 1
    src.flagged += flagged
    return ev


def _graph():
    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import GraphBuilder
        return GraphBuilder(neo4j_driver())
    except Exception:  # noqa: BLE001
        return None


def tick(session, now: float | None = None, *, telegram_fetch=None, graph=False) -> dict:
    """Poll every due source once and check its new posts."""
    from app.db.models import MonitorEvent, MonitorSource

    now = now or time.time()
    if telegram_fetch is None:
        from app.services.telegram_web import fetch_channel as telegram_fetch
    g = _graph() if graph else None
    polled = scanned = flagged = 0
    for src in session.query(MonitorSource).filter_by(active=True).order_by(MonitorSource.id):
        if src.last_polled_ts and now - src.last_polled_ts < src.interval_seconds:   # never polled → due
            continue
        src.last_polled_ts = now
        polled += 1
        try:
            posts = _fetch(src, telegram_fetch)
            src.last_error = ""
        except Exception as exc:  # noqa: BLE001 — one broken source never stops the monitor
            src.last_error = str(exc)[:250]
            continue
        for post in posts:
            ev = check_post(session, src, post, now, g)
            if ev is not None:
                scanned += 1
                flagged += ev.flagged
        session.commit()
    newest = session.query(MonitorEvent.id).order_by(MonitorEvent.id.desc()).first()
    if newest and newest[0] > KEEP_EVENTS:
        session.query(MonitorEvent).filter(MonitorEvent.id <= newest[0] - KEEP_EVENTS).delete(
            synchronize_session=False)
        session.commit()
    return {"polled": polled, "scanned": scanned, "flagged": flagged}


# ---- read side ---------------------------------------------------------------------
def event_dict(ev, sources: dict[int, object] | None = None) -> dict:
    src = (sources or {}).get(ev.source_id)
    return {"id": ev.id, "source_id": ev.source_id, "platform": ev.platform, "author": ev.author,
            "title": getattr(src, "title", "") or ev.author, "url": ev.url, "text": ev.text, "views": ev.views,
            "score": ev.score, "threat_level": ev.threat_level, "track": ev.track, "lang": ev.lang,
            "flagged": ev.flagged, "signals": ev.signals or [], "breakdown": ev.breakdown or [],
            "content_id": ev.content_id, "ts": ev.created_ts}


def feed(session, *, after: int = 0, since: float = 0.0, flagged_only: bool = True, track: str = "",
         limit: int = 40) -> list[dict]:
    from app.db.models import MonitorEvent, MonitorSource

    q = session.query(MonitorEvent).filter(MonitorEvent.id > after, MonitorEvent.created_ts >= since)
    if flagged_only:
        q = q.filter(MonitorEvent.flagged.is_(True))
    if track:
        q = q.filter(MonitorEvent.track == track)
    rows = q.order_by(MonitorEvent.id.desc()).limit(max(1, min(limit, 200))).all()
    sources = {s.id: s for s in session.query(MonitorSource)}
    return [event_dict(e, sources) for e in rows]


def status(session, now: float | None = None) -> dict:
    from sqlalchemy import func

    from app.db.models import MonitorEvent, MonitorSource

    now = now or time.time()
    since = started_at(session)
    base = session.query(MonitorEvent).filter(MonitorEvent.created_ts >= since)
    scanned = base.count()
    by = {t: {"high": 0, "medium": 0} for t in ("lottery", "casino", "pyramid")}
    for track, level, n in (session.query(MonitorEvent.track, MonitorEvent.threat_level, func.count())
                            .filter(MonitorEvent.created_ts >= since, MonitorEvent.flagged.is_(True))
                            .group_by(MonitorEvent.track, MonitorEvent.threat_level)):
        if track in by:
            by[track]["high" if level in ("HIGH", "CRITICAL") else "medium"] += n
    flagged = sum(v["high"] + v["medium"] for v in by.values())
    start_min = int(now // 60) - TIMELINE_MINUTES + 1
    buckets = {m: {"lottery": 0, "casino": 0, "pyramid": 0, "clean": 0}
               for m in range(start_min, start_min + TIMELINE_MINUTES)}
    for ts, track, is_flag in (session.query(MonitorEvent.created_ts, MonitorEvent.track, MonitorEvent.flagged)
                               .filter(MonitorEvent.created_ts >= start_min * 60)):
        b = buckets.get(int(ts // 60))
        if b is not None:
            b[track if is_flag and track in b else "clean"] += 1
    sources = []
    for s in session.query(MonitorSource).order_by(MonitorSource.id):
        sources.append({"id": s.id, "platform": s.platform, "handle": s.handle, "title": s.title,
                        "connector": s.connector, "active": s.active, "interval_seconds": s.interval_seconds,
                        "scanned": s.scanned, "flagged": s.flagged, "last_polled_ts": s.last_polled_ts or None,
                        "last_error": s.last_error})
    return {"enabled": is_enabled(session), "started_at": since or None, "scanned": scanned, "flagged": flagged,
            "by_track": by, "timeline": [{"minute": m * 60, **v} for m, v in buckets.items()],
            "sources": sources, "active_sources": sum(1 for s in sources if s["active"])}
