"""Persistence for the hash-chained audit log (append-only `audit_log` table).

Bridges the pure chain (services/audit.py) to Postgres. The table's INSERT-only
trigger (Alembic migration) enforces immutability at the DB layer; this repo only
ever reads the tail and appends.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AuditLogEntry
from app.services.audit import AuditEntry, AuditLog


class SqlAuditRepo:
    def __init__(self, session: Session):
        self.session = session

    def last_entry(self) -> AuditEntry | None:
        row = (
            self.session.query(AuditLogEntry)
            .order_by(AuditLogEntry.seq.desc())
            .first()
        )
        if row is None:
            return None
        return AuditEntry(row.seq, row.ts, row.actor, row.action, row.target,
                          row.prev_hash, row.entry_hash)

    def append(self, entry: AuditEntry) -> None:
        self.session.add(AuditLogEntry(
            seq=entry.seq, ts=entry.ts, actor=entry.actor, action=entry.action,
            target=entry.target, prev_hash=entry.prev_hash, entry_hash=entry.entry_hash,
        ))
        self.session.commit()


def record_action(session: Session, actor: str, action: str, target: str,
                  ts: str | None = None) -> AuditEntry:
    """Append one audit entry for an analyst action. Mandatory (fail-closed)."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    return AuditLog(SqlAuditRepo(session)).record(ts, actor, action, target)
