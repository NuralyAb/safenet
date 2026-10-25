"""Watchlist — the set of accounts/keywords the system continuously monitors.

The scheduler (Celery beat) sweeps active targets and dispatches ingestion for
each. Account targets are fetched directly; keyword targets are discovered via
search (proactive — finds NEW objects, not only known @handles).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import WatchTarget

VALID_KINDS = {"account", "keyword"}


def list_active(session: Session) -> list[WatchTarget]:
    return session.query(WatchTarget).filter_by(active=True).order_by(WatchTarget.id).all()


def list_all(session: Session) -> list[WatchTarget]:
    return session.query(WatchTarget).order_by(WatchTarget.id).all()


MIN_INTERVAL_SECONDS = 60


def _validate_schedule(interval_seconds: int | None, video_limit: int | None) -> None:
    if interval_seconds is not None and interval_seconds < MIN_INTERVAL_SECONDS:
        raise ValueError(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}")
    if video_limit is not None and not (1 <= video_limit <= 200):
        raise ValueError("video_limit must be between 1 and 200")


def add_target(session: Session, source: str, kind: str, value: str, added_by: str,
               interval_seconds: int | None = None, video_limit: int | None = None) -> WatchTarget:
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    _validate_schedule(interval_seconds, video_limit)
    existing = (
        session.query(WatchTarget)
        .filter_by(source=source, kind=kind, value=value)
        .one_or_none()
    )
    if existing is not None:
        existing.active = True            # re-activate instead of duplicating
        if interval_seconds is not None:
            existing.interval_seconds = interval_seconds
        if video_limit is not None:
            existing.video_limit = video_limit
        session.commit()
        return existing
    target = WatchTarget(source=source, kind=kind, value=value, added_by=added_by, active=True,
                         interval_seconds=interval_seconds, video_limit=video_limit)
    session.add(target)
    session.commit()
    return target


def update_target(session: Session, target_id: int, *, interval_seconds: int | None = None,
                  video_limit: int | None = None, active: bool | None = None,
                  clear_interval: bool = False, clear_limit: bool = False) -> WatchTarget | None:
    """Partial update of a target's schedule. clear_* reset a field to the global default."""
    target = session.get(WatchTarget, target_id)
    if target is None:
        return None
    _validate_schedule(interval_seconds, video_limit)
    if clear_interval:
        target.interval_seconds = None
    elif interval_seconds is not None:
        target.interval_seconds = interval_seconds
    if clear_limit:
        target.video_limit = None
    elif video_limit is not None:
        target.video_limit = video_limit
    if active is not None:
        target.active = active
    session.commit()
    return target


def deactivate(session: Session, target_id: int) -> bool:
    target = session.get(WatchTarget, target_id)
    if target is None:
        return False
    target.active = False
    session.commit()
    return True


def mark_run(session: Session, target_id: int, ts: str) -> None:
    target = session.get(WatchTarget, target_id)
    if target is not None:
        target.last_run_at = ts
        session.commit()
