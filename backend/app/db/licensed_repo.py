"""Persistence for the imported licensed-operator registry.

Idempotent upsert by normalized identifier; `active_identifiers` is the set the
license check consults (active rows ∪ the configured env allowlist). A suspended/
revoked licence is excluded — so it correctly reads as «нелицензионный».
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import LicensedEntity
from app.services.license_registry import _norm

VALID_STATUS = {"active", "suspended", "revoked"}


def upsert_entity(session: Session, identifier: str, *, kind: str = "domain",
                  operator: str = "", bin: str | None = None, license_no: str | None = None,
                  status: str = "active", source: str = "") -> LicensedEntity | None:
    """Upsert one operator identifier. Returns None for a blank identifier (skipped)."""
    ident = _norm(identifier)
    if not ident:
        return None
    if status not in VALID_STATUS:
        status = "active"
    row = session.query(LicensedEntity).filter_by(identifier=ident).one_or_none()
    if row is None:
        row = LicensedEntity(identifier=ident)
        session.add(row)
    row.kind = kind or "domain"
    row.operator = operator or ""
    row.bin = bin or None
    row.license_no = license_no or None
    row.status = status
    row.source = source or ""
    return row


def import_rows(session: Session, rows: list[dict], *, source: str = "") -> dict:
    """Bulk idempotent import. Each row: {identifier, kind?, operator?, bin?, license_no?, status?}.
    Returns {imported, skipped}. Commits once."""
    imported = skipped = 0
    for r in rows:
        ent = upsert_entity(
            session, r.get("identifier", ""),
            kind=r.get("kind", "domain"), operator=r.get("operator", ""),
            bin=r.get("bin"), license_no=r.get("license_no"),
            status=r.get("status", "active"), source=r.get("source", source),
        )
        if ent is None:
            skipped += 1
        else:
            imported += 1
    session.commit()
    return {"imported": imported, "skipped": skipped}


def active_identifiers(session: Session) -> set[str]:
    """Normalized identifiers that count as licensed = active DB rows ∪ env allowlist."""
    rows = session.query(LicensedEntity.identifier).filter_by(status="active").all()
    ids = {r[0] for r in rows}
    ids.update(_norm(x) for x in settings.licensed_registry if x)
    return ids


def load_active_identifiers() -> list[str] | None:
    """Open a short-lived session and return active identifiers (DB-aware callers
    without a session use this). Best-effort: any error returns None so the license
    check falls back to the configured client instead of flagging everyone."""
    try:
        from app.db.session import get_session
        gen = get_session()
        session = next(gen)
        try:
            return list(active_identifiers(session))
        finally:
            gen.close()
    except Exception:  # noqa: BLE001
        return None
