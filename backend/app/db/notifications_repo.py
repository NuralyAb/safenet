"""Persistence for watchlist notifications ('new video for a monitored account').

Idempotent by content_id so re-sweeping the same video never re-notifies. The
sweep/ingest pipeline calls record_new_video(); the API reads/marks them read.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import WatchlistNotification, WatchTarget


def _norm_handle(value: str) -> str:
    """Normalise a handle for matching: drop a leading @ and lowercase.

    yt-dlp stores the uploader id WITHOUT the @ (e.g. "amidom4ru") while a watch
    target is usually entered WITH it ("@amidom4ru") — compare them apples-to-apples.
    """
    return (value or "").strip().lstrip("@").lower()


def _is_watched_account(session: Session, author: str) -> bool:
    """True if `author` is an active account watch-target (@- and case-insensitive)."""
    if not author:
        return False
    a = _norm_handle(author)
    targets = session.query(WatchTarget.value).filter(
        WatchTarget.active.is_(True), WatchTarget.kind == "account",
    ).all()
    return any(_norm_handle(v) == a for (v,) in targets)


def _record(session: Session, *, content_id: str, author: str, source: str, url: str,
            score: int | None, threat_level: str | None, reason: str) -> WatchlistNotification | None:
    if not content_id:
        return None
    if session.query(WatchlistNotification.id).filter_by(content_id=content_id).first():
        return None
    row = WatchlistNotification(
        content_id=content_id, author=author or "", source=source or "", url=url or "",
        score=score, threat_level=threat_level, reason=reason,
    )
    session.add(row)
    session.commit()
    return row


def record_new_video(session: Session, *, content_id: str, author: str, source: str = "",
                     url: str = "", score: int | None = None,
                     threat_level: str | None = None) -> WatchlistNotification | None:
    """Record a 'new video from a monitored account' alert (idempotent per content).
    Returns the row, or None if the author isn't watched / already notified."""
    if not _is_watched_account(session, author):
        return None
    return _record(session, content_id=content_id, author=author, source=source, url=url,
                   score=score, threat_level=threat_level, reason="watched")


def maybe_alert(session: Session, *, content_id: str, author: str, source: str = "",
                url: str = "", score: int | None = None, threat_level: str | None = None,
                min_score: int = 65) -> WatchlistNotification | None:
    """The radar-agent alert rule: fire if the author is monitored (reason=watched)
    OR the content scores at/above the alert threshold (reason=high_risk). Idempotent
    per content_id; best-effort. This is what turns proactive discovery into «агент
    нашёл мошенничество → алерт»."""
    watched = _is_watched_account(session, author)
    high = score is not None and score >= min_score
    if not (watched or high):
        return None
    reason = "watched" if watched else "high_risk"
    return _record(session, content_id=content_id, author=author, source=source, url=url,
                   score=score, threat_level=threat_level, reason=reason)


def list_notifications(session: Session, *, unread_only: bool = False,
                       limit: int = 50) -> list[WatchlistNotification]:
    q = session.query(WatchlistNotification)
    if unread_only:
        q = q.filter(WatchlistNotification.read_at.is_(None))
    return q.order_by(WatchlistNotification.created_at.desc()).limit(limit).all()


def unread_count(session: Session) -> int:
    return session.query(WatchlistNotification).filter(
        WatchlistNotification.read_at.is_(None)).count()


def mark_read(session: Session, notif_id: int) -> WatchlistNotification | None:
    row = session.get(WatchlistNotification, notif_id)
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        session.commit()
    return row


def mark_all_read(session: Session) -> int:
    n = session.query(WatchlistNotification).filter(
        WatchlistNotification.read_at.is_(None)
    ).update({WatchlistNotification.read_at: datetime.now(timezone.utc)})
    session.commit()
    return n
