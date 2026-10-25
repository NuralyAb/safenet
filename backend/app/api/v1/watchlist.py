"""Watchlist endpoints — manage continuously-monitored accounts/keywords."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session
from app.services import watchlist

router = APIRouter()


class WatchTargetIn(BaseModel):
    source: str            # youtube | telegram | tiktok | instagram
    kind: str              # "account" | "keyword"
    value: str             # @handle or search query
    interval_seconds: int | None = None   # per-target cadence (null = global default)
    video_limit: int | None = None        # per-target videos/collection (null = global)


class WatchTargetPatch(BaseModel):
    interval_seconds: int | None = None
    video_limit: int | None = None
    active: bool | None = None
    clear_interval: bool = False          # reset interval to the global default
    clear_limit: bool = False             # reset limit to the global default


class WatchTargetOut(BaseModel):
    id: int
    source: str
    kind: str
    value: str
    active: bool
    last_run_at: str | None = None
    interval_seconds: int | None = None       # null = uses the global default
    effective_interval_seconds: int = 0       # resolved cadence actually applied
    video_limit: int | None = None            # null = uses the global default
    next_run_at: str | None = None            # ISO, computed from last_run + interval


class ScheduleOut(BaseModel):
    enabled: bool          # master on/off for auto-collection
    interval_seconds: int  # how often the sweep runs
    last_sweep: int        # epoch seconds of the last actual sweep (0 = never)
    next_sweep: int        # epoch seconds of the next due sweep (0 = disabled)


class ScheduleIn(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None


def _default_interval(session) -> int:
    from app.core.config import settings
    from app.db import settings_repo as cfg
    return cfg.get_int(session, cfg.SWEEP_INTERVAL, settings.watchlist_sweep_seconds)


def _to_out(t, default_interval: int) -> WatchTargetOut:
    from datetime import datetime, timedelta
    eff = t.interval_seconds or default_interval
    next_run = None
    if t.active:
        if t.last_run_at:
            try:
                next_run = (datetime.fromisoformat(t.last_run_at) + timedelta(seconds=eff)).isoformat()
            except ValueError:
                next_run = None
        else:
            next_run = "—"   # never run → due on the next tick
    return WatchTargetOut(id=t.id, source=t.source, kind=t.kind, value=t.value,
                          active=t.active, last_run_at=t.last_run_at,
                          interval_seconds=t.interval_seconds, effective_interval_seconds=eff,
                          video_limit=t.video_limit, next_run_at=next_run)


@router.get("", response_model=list[WatchTargetOut])
def list_watchlist(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> list[WatchTargetOut]:
    di = _default_interval(session)
    return [_to_out(t, di) for t in watchlist.list_all(session)]


@router.post("", response_model=WatchTargetOut)
def add_watch(
    body: WatchTargetIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> WatchTargetOut:
    try:
        t = watchlist.add_target(session, body.source, body.kind, body.value, principal.subject,
                                 interval_seconds=body.interval_seconds, video_limit=body.video_limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_action(session, principal.subject, "watchlist.add", f"{body.source}:{body.kind}:{body.value}")
    return _to_out(t, _default_interval(session))


@router.patch("/{target_id}", response_model=WatchTargetOut)
def patch_watch(
    target_id: int,
    body: WatchTargetPatch,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> WatchTargetOut:
    """Edit a target's own schedule — interval, video limit, or active state."""
    try:
        t = watchlist.update_target(
            session, target_id, interval_seconds=body.interval_seconds, video_limit=body.video_limit,
            active=body.active, clear_interval=body.clear_interval, clear_limit=body.clear_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if t is None:
        raise HTTPException(status_code=404, detail="Not found")
    record_action(session, principal.subject, "watchlist.update", str(target_id))
    return _to_out(t, _default_interval(session))


@router.delete("/{target_id}")
def remove_watch(
    target_id: int,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    if not watchlist.deactivate(session, target_id):
        raise HTTPException(status_code=404, detail="Not found")
    record_action(session, principal.subject, "watchlist.remove", str(target_id))
    return {"removed": target_id}


def _schedule(session: Session) -> ScheduleOut:
    import time

    from app.core.config import settings
    from app.db import settings_repo as cfg

    enabled = cfg.get_bool(session, cfg.SWEEP_ENABLED, cfg.SWEEP_ENABLED_DEFAULT)
    interval = cfg.get_int(session, cfg.SWEEP_INTERVAL, settings.watchlist_sweep_seconds)
    last = cfg.get_int(session, cfg.SWEEP_LAST_RUN, 0)
    nxt = (last + interval) if (enabled and last) else (int(time.time()) + interval if enabled else 0)
    return ScheduleOut(enabled=enabled, interval_seconds=interval, last_sweep=last, next_sweep=nxt)


@router.get("/schedule", response_model=ScheduleOut)
def get_schedule(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> ScheduleOut:
    """Current auto-collection schedule (on/off + interval + next run)."""
    return _schedule(session)


class ScheduleAction(ScheduleOut):
    dispatched: int = 0        # targets sent for collection right now («Запустить»)


@router.post("/schedule/start", response_model=ScheduleAction)
def start_auto_collection(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> ScheduleAction:
    """«Запустить автосбор»: enable it and sweep every active target immediately."""
    from app.db import settings_repo as cfg
    from app.services.watchlist import list_active

    cfg.set(session, cfg.SWEEP_ENABLED, "true")
    targets = len(list_active(session))
    try:
        from app.workers.tasks import sweep_watchlist
        sweep_watchlist.delay(force=True)
    except Exception as exc:  # noqa: BLE001 — broker down: setting is on, beat will pick it up
        raise HTTPException(status_code=503, detail=f"Очередь задач недоступна: {exc}") from exc
    record_action(session, principal.subject, "watchlist.start", f"targets={targets}")
    return ScheduleAction(**_schedule(session).model_dump(), dispatched=targets)


@router.post("/schedule/stop", response_model=ScheduleAction)
def stop_auto_collection(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> ScheduleAction:
    """«Остановить автосбор»: disable it; queued auto-collection work is dropped by the
    workers before any download or paid AI call (manual collections are unaffected)."""
    from app.db import settings_repo as cfg

    cfg.set(session, cfg.SWEEP_ENABLED, "false")
    record_action(session, principal.subject, "watchlist.stop", "")
    return ScheduleAction(**_schedule(session).model_dump())


@router.put("/schedule", response_model=ScheduleOut)
def set_schedule(
    body: ScheduleIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> ScheduleOut:
    """Tune auto-collection from the UI — beat picks it up on the next 60s tick."""
    from app.db import settings_repo as cfg

    if body.interval_seconds is not None:
        if body.interval_seconds < cfg.MIN_INTERVAL_SECONDS:
            raise HTTPException(status_code=422,
                                detail=f"interval_seconds must be >= {cfg.MIN_INTERVAL_SECONDS}")
        cfg.set(session, cfg.SWEEP_INTERVAL, str(int(body.interval_seconds)))
    if body.enabled is not None:
        cfg.set(session, cfg.SWEEP_ENABLED, "true" if body.enabled else "false")
    record_action(session, principal.subject, "watchlist.schedule",
                  f"enabled={body.enabled} interval={body.interval_seconds}")
    return _schedule(session)


# --- Notifications: 'new video for a monitored account' (toast alerts) -----------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    content_id: str
    author: str
    source: str
    url: str
    score: int | None = None
    threat_level: str | None = None
    reason: str = "watched"
    created_at: datetime | None = None
    read_at: datetime | None = None


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = True,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> list:
    """New-video alerts for monitored accounts (newest first). Drives the toast."""
    from app.db import notifications_repo as notif
    return notif.list_notifications(session, unread_only=unread_only, limit=50)


@router.post("/notifications/read-all")
def read_all_notifications(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Dismiss all unread alerts."""
    from app.db import notifications_repo as notif
    return {"marked_read": notif.mark_all_read(session)}


@router.post("/notifications/{notif_id}/read", response_model=NotificationOut)
def read_notification(
    notif_id: int,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> object:
    """Dismiss one alert."""
    from app.db import notifications_repo as notif
    row = notif.mark_read(session, notif_id)
    if row is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return row
