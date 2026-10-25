"""SQLAlchemy 2.0 models — relational source of truth + audit.

Tables:
  users            analysts/supervisors/admins (argon2 hash + TOTP secret)
  content          one collected item (links to evidence + author)
  evidence         chain-of-custody record (sha256, WORM key, optional signature)
  risk_assessment  explainable score snapshot (factor breakdown as JSON)
  audit_log        append-only, hash-chained (see services/audit.py)

The audit_log is INSERT-only — enforced at the DB layer by a trigger in the
Alembic migration (Postgres). Application code never UPDATEs/DELETEs it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))            # Role enum value
    password_hash: Mapped[str] = mapped_column(Text)         # argon2id
    totp_secret: Mapped[str] = mapped_column(String(64))     # base32 TOTP seed
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Content(Base):
    __tablename__ = "content"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)   # content_id
    source: Mapped[str] = mapped_column(String(32), index=True)     # youtube/telegram/...
    external_id: Mapped[str] = mapped_column(String(256))
    author: Mapped[str] = mapped_column(String(256), index=True)
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # Retained analysis text (evidentiary — an analyst must be able to re-read what
    # was said/shown in the clip). transcript = speech (Whisper); ocr_text = on-screen
    # text across sampled frames; tags = visual object tags. Nullable for old rows.
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)     # original post / message text

    # NLP claim flags (extracted by the LLM at process time -> risk factors)
    promises_returns: Mapped[bool] = mapped_column(Boolean, default=False)
    has_referral: Mapped[bool] = mapped_column(Boolean, default=False)
    has_license: Mapped[bool] = mapped_column(Boolean, default=False)
    gambling_content: Mapped[bool] = mapped_column(Boolean, default=False)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="content")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("content.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    evidence_key: Mapped[str] = mapped_column(Text)          # WORM object key
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(128))
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)  # Ed25519 (Phase E)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    content: Mapped["Content"] = relationship(back_populates="evidence")


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(256), unique=True, index=True)  # one row per object
    score: Mapped[int] = mapped_column(Integer, index=True)
    threat_level: Mapped[str] = mapped_column(String(16))
    breakdown: Mapped[list] = mapped_column(JSON)                  # per-factor + evidence_ids
    recommendation: Mapped[str] = mapped_column(Text)
    # Triage workflow: analyst disposition on the object.
    disposition: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    disposition_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class ContentRisk(Base):
    """Per-VIDEO explainable score — the unit the ТЗ asks to score and prioritise.

    Mirrors RiskAssessment but keyed by content (one collected video/post). The
    account-level RiskAssessment is the roll-up; this is the material an analyst
    triages. `content_id` is a plain indexed string (no hard FK) — like
    RiskAssessment.target — so it survives even when the live pipeline scores
    content before a Content row is persisted.
    """
    __tablename__ = "content_risk"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    author: Mapped[str] = mapped_column(String(256), index=True, default="")
    source: Mapped[str] = mapped_column(String(32), index=True, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, index=True)
    threat_level: Mapped[str] = mapped_column(String(16))
    breakdown: Mapped[list] = mapped_column(JSON)                  # per-factor + evidence_ids
    recommendation: Mapped[str] = mapped_column(Text)
    # Audience reach («охват») — drives triage priority (risk × reach), not the risk score.
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, index=True, default=0)   # triage sort key
    # SafeNet KZ: which scheme the signs point to (lottery | casino | pyramid | "") + language
    track: Mapped[str] = mapped_column(String(16), index=True, default="")
    lang: Mapped[str] = mapped_column(String(16), default="")
    disposition: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    disposition_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class WatchTarget(Base):
    """A target the system continuously monitors: an account or a keyword/hashtag."""
    __tablename__ = "watch_target"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)   # youtube/telegram/...
    kind: Mapped[str] = mapped_column(String(16))                 # "account" | "keyword"
    value: Mapped[str] = mapped_column(String(256))              # @handle or search query
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    last_run_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Per-target schedule. interval_seconds = how often THIS target is swept
    # (null -> use the global default). video_limit = videos per collection
    # (null -> global collect_video_limit). Lets each account run on its own cadence.
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WatchlistNotification(Base):
    """A 'new video detected for a monitored account' event, surfaced as a toast.

    Written when the sweep (or any ingest) creates a brand-new Content row whose
    author is an active account WatchTarget. One row per (content) so re-sweeping
    the same video never re-notifies. `read_at` nullable → unread until dismissed.
    """
    __tablename__ = "watchlist_notification"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    author: Mapped[str] = mapped_column(String(256), index=True)
    source: Mapped[str] = mapped_column(String(32), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threat_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Why this alert fired: "watched" (new video from a monitored account) or
    # "high_risk" (proactive radar found content scoring >= the alert threshold).
    reason: Mapped[str] = mapped_column(String(16), default="watched")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)


class AppSetting(Base):
    """Runtime-configurable settings (key→value), editable from the UI.

    Used for the continuous-monitoring schedule (interval + on/off) so analysts can
    tune auto-collection without an env change + restart. Beat reads these each tick.
    """
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class LicensedEntity(Base):
    """A licensed operator imported from a regulator registry (e.g. АРРФР).

    The registry keys on legal name + BIN, but our content matches on the
    identifiers that actually appear in videos (domain / @handle). So each row maps
    ONE such identifier to a license, carrying the operator/BIN/license metadata and
    a `status` — a revoked/suspended licence must NOT count as licensed. Refreshed
    by `scripts/import_licensed_registry.py` (idempotent upsert by identifier).
    """
    __tablename__ = "licensed_entity"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier: Mapped[str] = mapped_column(String(256), unique=True, index=True)  # normalized: lowercase, no @
    kind: Mapped[str] = mapped_column(String(16), default="domain")   # domain | handle | name | bin
    operator: Mapped[str] = mapped_column(String(256), default="")    # legal name from the registry
    bin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    license_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|suspended|revoked
    source: Mapped[str] = mapped_column(String(32), default="")       # ardfm | egov | manual
    imported_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    ts: Mapped[str] = mapped_column(String(40))               # ISO-8601 UTC
    actor: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(256))
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
