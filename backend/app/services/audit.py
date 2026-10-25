"""Tamper-evident audit log (hash-chained, append-only).

Every analyst action (login, launch investigation, view target, confirm a
SAME_PERSON link, access the biometric vault) is recorded. Each entry hashes the
previous entry's hash, so any edit/deletion of history breaks the chain and is
detectable — essential non-repudiation for a surveillance tool.

The chaining + verification are pure (stdlib) and unit-tested; persistence to an
append-only Postgres table is a thin wrapper.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    ts: str               # ISO-8601 UTC, supplied by caller
    actor: str            # analyst id
    action: str           # e.g. "investigation.open", "biometric.view"
    target: str           # subject of the action
    prev_hash: str
    entry_hash: str


def _hash(seq: int, ts: str, actor: str, action: str, target: str, prev_hash: str) -> str:
    canonical = json.dumps(
        [seq, ts, actor, action, target, prev_hash], separators=(",", ":"), sort_keys=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def make_entry(prev: AuditEntry | None, ts: str, actor: str, action: str, target: str) -> AuditEntry:
    seq = 0 if prev is None else prev.seq + 1
    prev_hash = GENESIS_HASH if prev is None else prev.entry_hash
    return AuditEntry(
        seq=seq, ts=ts, actor=actor, action=action, target=target,
        prev_hash=prev_hash,
        entry_hash=_hash(seq, ts, actor, action, target, prev_hash),
    )


def verify_chain(entries: list[AuditEntry]) -> bool:
    """True iff the chain is intact (no tampered/missing/reordered entries)."""
    prev: AuditEntry | None = None
    for e in entries:
        expected = make_entry(prev, e.ts, e.actor, e.action, e.target)
        if (e.seq, e.prev_hash, e.entry_hash) != (expected.seq, expected.prev_hash, expected.entry_hash):
            return False
        prev = e
    return True


class AuditLog:
    """Append-only persistence wrapper around the pure chain (Phase 0: Postgres)."""

    def __init__(self, repo):
        self.repo = repo   # must enforce INSERT-only (no UPDATE/DELETE grants)

    def record(self, ts: str, actor: str, action: str, target: str) -> AuditEntry:
        prev = self.repo.last_entry()
        entry = make_entry(prev, ts, actor, action, target)
        self.repo.append(entry)
        return entry
