"""Runtime settings (app_setting key→value) with typed helpers.

The continuous-monitoring schedule lives here so it's editable from the UI and
read by Celery beat each tick — no env change / restart needed.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AppSetting

# Setting keys + sane defaults (fallback when no row exists yet).
SWEEP_INTERVAL = "watchlist_sweep_seconds"   # how often auto-collection runs
SWEEP_ENABLED = "watchlist_enabled"          # master on/off for auto-collection
SWEEP_LAST_RUN = "watchlist_last_sweep"      # epoch seconds of the last actual sweep
# Auto-collection is OFF until an analyst presses «Запустить»: every sweep spends paid
# AI calls (STT / vision / LLM), so it must never start on its own.
SWEEP_ENABLED_DEFAULT = False

MIN_INTERVAL_SECONDS = 60                     # floor — beat ticks every 60s


def get(session: Session, key: str) -> str | None:
    row = session.get(AppSetting, key)
    return row.value if row else None


def set(session: Session, key: str, value: str) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    session.commit()


def get_int(session: Session, key: str, default: int) -> int:
    raw = get(session, key)
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def get_bool(session: Session, key: str, default: bool) -> bool:
    raw = get(session, key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")
