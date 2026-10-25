"""License registry check endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.licensed_repo import active_identifiers
from app.db.session import get_session
from app.services.license_registry import check_licensed

router = APIRouter()


@router.get("/check")
def check(
    q: str,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Verify an entity (domain / handle / name) against the licensed registry —
    the imported АРРФР data (active rows) plus the configured allowlist."""
    return check_licensed([q], registry=list(active_identifiers(session)))
