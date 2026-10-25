"""Settings endpoints — list and edit runtime-configurable knobs from the UI.

Backed by the `app_setting` table via `runtime_config`. Workers read the effective
values on their next task, so changes apply without a restart.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session
from app.services import runtime_config

router = APIRouter()


class SettingsUpdate(BaseModel):
    updates: dict[str, object]   # {key: value} — validated against the registry


@router.get("")
def list_settings(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Every tunable setting with its current effective value, grouped for the UI."""
    return {"settings": runtime_config.describe(session)}


@router.put("")
def update_settings(
    body: SettingsUpdate,
    # Prototype: any authenticated analyst may tune settings (incl. the dev_mode
    # demo toggle). PRODUCTION: restore require_role(Role.SUPERVISOR)/ADMIN — config
    # is a privileged action. Every change is still recorded in the audit log below.
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = runtime_config.apply(session, body.updates)
    except runtime_config.UnknownSetting as exc:
        raise HTTPException(status_code=422, detail=f"Unknown setting: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_action(session, principal.subject, "settings.update",
                  ",".join(sorted(body.updates.keys())))
    return {"settings": result}
