"""Evidence store — chain of custody for collected artifacts.

Every original is SHA-256 hashed at collection time and written to two buckets:
  - raw/       working copy for the processing pipeline
  - evidence/  WORM (object-lock) copy that must survive post deletion

Storage is **content-addressed** (key derived from the hash), which makes
ingestion idempotent: re-collecting identical bytes is a no-op, and the same
content always maps to the same evidence key.

The hashing + key derivation are pure and unit-tested; `EvidenceStore` wraps the
MinIO client for the I/O.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

# WORM retention for evidence objects. COMPLIANCE = immutable even to root.
EVIDENCE_RETENTION_DAYS = 3650


@dataclass(frozen=True)
class EvidenceRef:
    sha256: str
    size: int
    raw_key: str
    evidence_key: str
    content_type: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_key(sha256: str, source: str, ext: str = "") -> str:
    """Content-addressed key: source/aa/bb/<full-hash>.<ext>.

    Sharding by the first hash bytes keeps any single prefix from growing huge.
    """
    ext = ext.lstrip(".")
    suffix = f".{ext}" if ext else ""
    return f"{source}/{sha256[:2]}/{sha256[2:4]}/{sha256}{suffix}"


class EvidenceStore:
    def __init__(self, client, raw_bucket: str, evidence_bucket: str):
        self.client = client                # minio.Minio
        self.raw_bucket = raw_bucket
        self.evidence_bucket = evidence_bucket

    def ensure_buckets(self) -> None:
        """Create buckets; the evidence bucket is object-locked (WORM)."""
        if not self.client.bucket_exists(self.raw_bucket):
            self.client.make_bucket(self.raw_bucket)
        if not self.client.bucket_exists(self.evidence_bucket):
            # object_lock=True is required for per-object retention (immutability).
            self.client.make_bucket(self.evidence_bucket, object_lock=True)

    def _exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.stat_object(bucket, key)
            return True
        except Exception:  # noqa: BLE001 — minio raises S3Error on missing object
            return False

    def store(
        self,
        data: bytes,
        source: str,
        content_type: str = "application/octet-stream",
        ext: str = "",
    ) -> EvidenceRef:
        """Hash, then idempotently write to raw + WORM evidence. Returns the ref."""
        import io
        from datetime import datetime, timedelta, timezone

        from minio.commonconfig import GOVERNANCE
        from minio.retention import Retention

        digest = sha256_bytes(data)
        key = evidence_key(digest, source, ext)
        size = len(data)

        if not self._exists(self.raw_bucket, key):
            self.client.put_object(
                self.raw_bucket, key, io.BytesIO(data), size, content_type=content_type
            )
        if not self._exists(self.evidence_bucket, key):
            retain_until = datetime.now(timezone.utc) + timedelta(days=EVIDENCE_RETENTION_DAYS)
            self.client.put_object(
                self.evidence_bucket, key, io.BytesIO(data), size,
                content_type=content_type,
                retention=Retention(GOVERNANCE, retain_until),
            )
        return EvidenceRef(
            sha256=digest, size=size, raw_key=key, evidence_key=key, content_type=content_type
        )
