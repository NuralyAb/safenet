"""Chain-of-custody index: link a Content row to its WORM evidence object.

The original bytes already live in MinIO (raw + object-locked evidence bucket,
written at collection time). This records the DB-side custody row so the link
content_id -> sha256 -> WORM key is queryable and auditable. Idempotent: one row
per (content_id, evidence_key); re-runs of the pipeline don't duplicate it.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evidence


def upsert_evidence(
    session: Session,
    content_id: str,
    sha256: str,
    evidence_key: str,
    size: int,
    content_type: str,
    signature: str | None = None,
) -> Evidence:
    """Create the custody row if absent; refresh metadata if it already exists."""
    row = session.scalar(
        select(Evidence).where(
            Evidence.content_id == content_id, Evidence.evidence_key == evidence_key
        )
    )
    if row is None:
        row = Evidence(content_id=content_id, evidence_key=evidence_key, sha256=sha256,
                       size=size, content_type=content_type, signature=signature)
        session.add(row)
    else:
        row.sha256 = sha256
        row.size = size
        row.content_type = content_type
        if signature is not None:
            row.signature = signature
    return row
