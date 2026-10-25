"""Autonomous hunt — launch proactive fraud discovery across search queries."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session

router = APIRouter()


class HuntIn(BaseModel):
    sources: list[str] | None = None      # subset of youtube/tiktok/instagram (default: all)
    count: int = 6
    limit: int = 4
    adapt: bool = False                    # next-round queries learned from found patterns


@router.post("")
def hunt(
    body: HuntIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Generate suspicious search queries (or adapt to found patterns) and fire
    keyword-discovery across the selected sources."""
    from app.services.hunter import run_hunt

    out = run_hunt(session, sources=body.sources, count=max(1, min(body.count, 12)),
                   limit=max(1, min(body.limit, 20)), adapt=body.adapt)
    record_action(session, principal.subject, "hunt.run",
                  f"{','.join(out['sources'])}:{out['count']}q:adapt={out['adapted']}")
    return out
