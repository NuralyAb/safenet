"""Ingestion pipeline: collect -> process -> fingerprint.

DataOps guardrails baked in:
  - idempotency   : content-addressed (SHA-256) so re-runs don't duplicate work
  - retries       : transient failures (network/inference) retried with backoff
  - dead-letter   : terminal failures recorded, never silently dropped
  - schema checks  : each stage validates its input shape before doing work

Tasks stay thin — real work lives in services (evidence, fingerprint, graph).
"""
from __future__ import annotations

import logging

from celery import Task, chain

from app.workers.celery_app import celery_app

log = logging.getLogger("afm.pipeline")

# Required keys each stage hands to the next — a lightweight data contract.
_COLLECT_OUT = {"content_id", "source", "sha256", "raw_key", "author"}
_PROCESS_OUT = {"content_id", "sha256", "features"}


def _require(payload: dict, keys: set[str], stage: str) -> None:
    missing = keys - payload.keys()
    if missing:
        raise ValueError(f"{stage}: payload missing keys {sorted(missing)}")


SWEEP_ORIGIN = "sweep"     # work started by auto-collection (vs a manual «Собрать»)


def sweep_stopped() -> bool:
    """True when the analyst has stopped auto-collection (or never started it)."""
    from app.db import settings_repo as cfg
    from app.db.session import get_session

    gen = get_session()
    session = next(gen)
    try:
        return not cfg.get_bool(session, cfg.SWEEP_ENABLED, cfg.SWEEP_ENABLED_DEFAULT)
    finally:
        gen.close()


def _cancel_if_sweep_stopped(origin: str | None, stage: str) -> None:
    """«Остановить» must stop spending at once: queued auto-collection work is dropped
    at the next stage, before any download or paid AI call. Manual runs are unaffected."""
    if origin == SWEEP_ORIGIN and sweep_stopped():
        from celery.exceptions import Ignore
        log.info("auto-collection stopped — dropping queued %s", stage)
        raise Ignore()


def _dead_letter(stage: str, payload, exc: Exception) -> None:
    """Record a terminally-failed item. Phase 0: also persist to a dead_letter table."""
    log.error("DEAD-LETTER stage=%s err=%s payload=%r", stage, exc, payload)


class PipelineTask(Task):
    """Base task: bounded retries + dead-letter on terminal failure."""
    autoretry_for = (ConnectionError, TimeoutError)
    retry_backoff = True
    retry_kwargs = {"max_retries": 3}
    acks_late = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        _dead_letter(self.name, args[0] if args else None, exc)


@celery_app.task(base=PipelineTask, name="app.workers.tasks.collect_content")
def collect_content(source: str, target: str, limit: int | None = None,
                    origin: str | None = None) -> list[dict]:
    """Fetch a target's content via the source adapter; store originals (WORM)."""
    _cancel_if_sweep_stopped(origin, "collect")
    import app.workers.collectors  # noqa: F401 — registers adapters
    from app.core.config import settings
    from app.db.clients import minio_client
    from app.services.evidence import EvidenceStore
    from app.workers.collectors.registry import get_collector
    from app.workers.collectors.runner import collect_via

    store = EvidenceStore(
        minio_client(), settings.minio_raw_bucket, settings.minio_evidence_bucket
    )
    from app.services import runtime_config as rc
    lim = limit or rc.get_value("collect_video_limit")
    if rc.get_value("ai_provider") == "mock":          # offline demo: no yt-dlp / network
        from app.services.dev_mock import mock_collect
        return mock_collect(source, target, lim, store)
    return collect_via(get_collector(source), store, target,
                       settings.collector_allowed_hosts, limit=lim)


@celery_app.task(base=PipelineTask, name="app.workers.tasks.discover_content")
def discover_content(source: str, query: str, limit: int | None = None,
                     origin: str | None = None) -> list[dict]:
    """Proactively discover NEW content by keyword/hashtag (not a known @handle)."""
    _cancel_if_sweep_stopped(origin, "discover")
    import app.workers.collectors  # noqa: F401 — registers adapters
    from app.core.config import settings
    from app.db.clients import minio_client
    from app.services.evidence import EvidenceStore
    from app.workers.collectors.registry import get_collector
    from app.workers.collectors.runner import discover_via

    store = EvidenceStore(
        minio_client(), settings.minio_raw_bucket, settings.minio_evidence_bucket
    )
    from app.services import runtime_config as rc
    lim = limit or rc.get_value("collect_video_limit")
    if rc.get_value("ai_provider") == "mock":          # offline demo: no yt-dlp / network
        from app.services.dev_mock import mock_collect
        return mock_collect(source, query, lim, store)
    return discover_via(get_collector(source), store, query,
                        settings.collector_allowed_hosts, limit=lim)


@celery_app.task(base=PipelineTask, name="app.workers.tasks.process_content")
def process_content(collected: dict) -> dict:
    """Embed the content's text (B1) -> features. STT/vision/OCR land in B2/B4."""
    _require(collected, _COLLECT_OUT, "process_content")
    _cancel_if_sweep_stopped(collected.get("origin"), "process")      # before any paid AI call
    from app.core.config import settings
    from app.db.clients import minio_client
    from app.services.ai.factory import (
        get_embedder,
        get_face_embedder,
        get_llm,
        get_ocr,
        get_speaker_embedder,
        get_transcriber,
        get_vision_tagger,
    )
    from app.db.licensed_repo import load_active_identifiers
    from app.services.media import enrich_with_media
    from app.services.pipeline import extract_features

    # Extract audio + a frame from the stored original (ffmpeg, isolated worker).
    def _fetch(raw_key: str) -> bytes:
        return minio_client().get_object(settings.minio_raw_bucket, raw_key).read()

    from app.services import runtime_config as rc
    collected = enrich_with_media(collected, _fetch, frames=int(rc.get_value("video_frames")))
    return extract_features(
        get_embedder(), collected,
        transcriber=get_transcriber(), vision=get_vision_tagger(), llm=get_llm(),
        face_embedder=get_face_embedder(), speaker_embedder=get_speaker_embedder(),
        ocr=get_ocr(), licensed_registry=load_active_identifiers(),
    )


@celery_app.task(base=PipelineTask, name="app.workers.tasks.fingerprint_content")
def fingerprint_content(processed: dict) -> dict:
    """Build the composite fingerprint, upsert to Qdrant, return scheme matches.

    Carries the per-video facts forward so the next stage (score_content) can
    compute the deterministic risk without re-reading the processed payload.
    """
    _require(processed, _PROCESS_OUT, "fingerprint_content")
    from app.db.clients import qdrant_client
    from app.services.fingerprint import FingerprintStore
    from app.services.pipeline import fingerprint_from_processed

    fp = fingerprint_from_processed(processed)
    store = FingerprintStore(qdrant_client())
    store.upsert(fp)
    matches = store.search_similar(fp)

    # Populate the Fraud Graph from extracted identifiers.
    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import GraphBuilder

        if processed.get("author"):
            from app.services.adhoc import graph_identifiers
            GraphBuilder(neo4j_driver()).link_identifiers(processed["author"], **graph_identifiers(processed))
    except Exception:  # noqa: BLE001
        pass

    facts = {**processed.get("claims", {}), **processed.get("signals", {})}
    related = len(processed.get("telegram", [])) + len(processed.get("wallets", [])) \
        + len(processed.get("domains", []))
    return {
        "content_id": fp.content_id,
        "matches": [m.content_id for m in matches],
        "facts": facts,
        "related_objects": related,
        "author": processed.get("author", ""),
        "source": processed.get("source", ""),
        "url": processed.get("url", ""),
        "reach": processed.get("reach", {}),
        # Retained evidence text + chain-of-custody fields for score_content to persist.
        "sha256": processed.get("sha256", fp.content_id),
        "transcript": processed.get("transcript", ""),
        "ocr_text": processed.get("ocr_text", ""),
        "caption": processed.get("caption", ""),
        "safenet": processed.get("safenet"),          # SafeNet signals with quotes
        "tags": processed.get("tags", []),
        "raw_key": processed.get("raw_key", ""),
        "evidence_key": processed.get("evidence_key", processed.get("raw_key", "")),
        "size": processed.get("size", 0),
        "content_type": processed.get("content_type", ""),
    }


@celery_app.task(base=PipelineTask, name="app.workers.tasks.score_content")
def score_content(fingerprinted: dict) -> dict:
    """Deterministic per-VIDEO risk -> content_risk (feeds the materials triage).

    Same Risk Engine as the account roll-up — the LLM never assigns the number.
    evidence_id traces back to this content so every point is defensible.
    """
    _require(fingerprinted, {"content_id", "facts"}, "score_content")
    from app.db.risk_repo import upsert_content_risk
    from app.db.session import get_session
    from app.services.content_scoring import score_content as _score

    a = _score(
        fingerprinted["facts"],
        safenet=fingerprinted.get("safenet"),
        scheme_matches=len(fingerprinted.get("matches", [])),
        related_objects=fingerprinted.get("related_objects", 0),
        evidence_ids=[fingerprinted["content_id"]],
    )
    gen = get_session()
    session = next(gen)
    try:
        upsert_content_risk(
            session, fingerprinted["content_id"], a.score, a.threat_level.value,
            a.breakdown, a.recommendation,
            author=fingerprinted.get("author", ""), source=fingerprinted.get("source", ""),
            url=fingerprinted.get("url", ""), reach=fingerprinted.get("reach", {}),
            track=a.track, lang=a.language,
        )
        # Also persist a Content row so the account & its videos feed /accounts
        # and the account-level investigation (which reads Content.author).
        from app.db.models import Content

        facts = fingerprinted.get("facts", {})
        cid = fingerprinted["content_id"]
        crow = session.get(Content, cid)
        is_new_content = crow is None
        if crow is None:
            crow = Content(id=cid, external_id=cid, sha256=cid)
            session.add(crow)
        crow.source = fingerprinted.get("source", "") or crow.source or "youtube"
        crow.author = fingerprinted.get("author", "") or crow.author or "(не указан)"
        crow.url = fingerprinted.get("url", "")
        crow.sha256 = fingerprinted.get("sha256", cid) or crow.sha256 or cid
        crow.lang = a.language or crow.lang or "ru"
        crow.caption = fingerprinted.get("caption") or crow.caption
        crow.transcript = fingerprinted.get("transcript") or crow.transcript
        crow.ocr_text = fingerprinted.get("ocr_text") or crow.ocr_text
        crow.tags = fingerprinted.get("tags") or crow.tags
        crow.promises_returns = bool(facts.get("promises_returns"))
        crow.has_referral = bool(facts.get("has_referral"))
        crow.has_license = bool(facts.get("has_license"))
        crow.gambling_content = bool(facts.get("gambling_content"))

        # Chain-of-custody row: link this content to its WORM evidence object.
        ev_key = fingerprinted.get("evidence_key") or fingerprinted.get("raw_key")
        if ev_key:
            from app.db.evidence_repo import upsert_evidence
            upsert_evidence(
                session, cid, fingerprinted.get("sha256", cid) or cid, ev_key,
                int(fingerprinted.get("size", 0) or 0), fingerprinted.get("content_type", ""),
            )
        session.commit()

        # Radar-agent alert on NEW content: fire if the author is monitored OR the
        # content scores at/above the alert threshold (proactive fraud detection).
        # Idempotent; best-effort — never fails scoring.
        if is_new_content:
            try:
                from app.db.notifications_repo import maybe_alert, record_new_video
                from app.services import runtime_config as rc

                if rc.get_value("alert_on_high_risk"):
                    maybe_alert(
                        session, content_id=cid, author=crow.author, source=crow.source,
                        url=crow.url, score=a.score, threat_level=a.threat_level.value,
                        min_score=int(rc.get_value("alert_min_score")),
                    )
                else:   # threshold alerts off → only monitored accounts notify
                    record_new_video(
                        session, content_id=cid, author=crow.author, source=crow.source,
                        url=crow.url, score=a.score, threat_level=a.threat_level.value,
                    )
            except Exception:  # noqa: BLE001 — notification is best-effort, never fail scoring
                session.rollback()
    finally:
        gen.close()
    return {"content_id": fingerprinted["content_id"], "score": a.score,
            "threat_level": a.threat_level.value, "track": a.track}


@celery_app.task(name="app.workers.tasks.fanout_items")
def fanout_items(items: list[dict], origin: str | None = None) -> int:
    """Fan out one process->fingerprint->score chain per collected item."""
    _cancel_if_sweep_stopped(origin, "fanout")
    for item in items:
        if origin:
            item = {**item, "origin": origin}
        chain(process_content.s(item), fingerprint_content.s(), score_content.s()).apply_async()
    return len(items)


def ingest(source: str, target: str, kind: str = "account", limit: int | None = None,
           origin: str | None = None):
    """Ingest one target: account → fetch, keyword → discover; then fan out per item.

    `origin="sweep"` marks auto-collection work so «Остановить» can cancel it."""
    first = (discover_content.s(source, target, limit, origin) if kind == "keyword"
             else collect_content.s(source, target, limit, origin))
    return chain(first, fanout_items.s(origin)).apply_async()


@celery_app.task(name="app.workers.tasks.sweep_watchlist")
def sweep_watchlist(force: bool = False) -> int:
    """Periodic (Celery beat, 60s tick): dispatch ingestion for every active target.

    `force=True` («Запустить» in the UI) runs every active target now instead of
    waiting for its interval.

    Self-gates on the UI-configurable schedule (app_setting): runs only when enabled
    AND at least `watchlist_sweep_seconds` has elapsed since the last sweep. Returns
    the number of targets dispatched, or -1 when skipped (disabled / not yet due).

    This is what makes collection CONTINUOUS and PROACTIVE — accounts are re-fetched
    and keywords are searched on a schedule, surfacing new objects in the network.
    """
    from datetime import datetime, timezone

    from app.core.config import settings
    from app.db import settings_repo as cfg
    from app.db.session import get_session
    from app.services.watchlist import list_active, mark_run

    def _last_epoch(ts: str | None) -> float:
        if not ts:
            return 0.0
        try:
            return datetime.fromisoformat(ts).timestamp()
        except ValueError:
            return 0.0

    gen = get_session()
    session = next(gen)
    try:
        if not cfg.get_bool(session, cfg.SWEEP_ENABLED, cfg.SWEEP_ENABLED_DEFAULT):
            return -1                                   # auto-collection paused from the UI
        default_interval = cfg.get_int(session, cfg.SWEEP_INTERVAL, settings.watchlist_sweep_seconds)
        now = datetime.now(timezone.utc)
        now_epoch = now.timestamp()

        dispatched = 0
        for t in list_active(session):
            interval = t.interval_seconds or default_interval     # per-target cadence
            if not force and now_epoch - _last_epoch(t.last_run_at) < interval:
                continue                                          # this target isn't due yet
            ingest(t.source, t.value, kind=t.kind, limit=t.video_limit,   # per-target limit
                   origin=SWEEP_ORIGIN)
            mark_run(session, t.id, now.isoformat())
            dispatched += 1
        if dispatched:
            cfg.set(session, cfg.SWEEP_LAST_RUN, str(int(now_epoch)))
        return dispatched
    finally:
        gen.close()


MONITOR_LOCK = "safenet:monitor:loop"


@celery_app.task(name="app.workers.tasks.collect_safenet_monitor")
def collect_safenet_monitor(max_seconds: int = 1500, pause: float = 2.0) -> int:
    """«Мониторинг схем» loop: while the analyst keeps it on, poll sources every ~2 s.

    Started by «Запустить мониторинг» and re-dispatched by beat every 30 s; a Redis
    lock keeps exactly one loop alive. Exits at once when the monitor is stopped.
    Returns the number of posts checked.
    """
    import time

    import redis

    from app.core.config import settings
    from app.db.session import get_session
    from app.services.safenet import monitor

    r = redis.Redis.from_url(settings.redis_url)
    if not r.set(MONITOR_LOCK, "1", nx=True, ex=30):
        return 0                                        # another loop is already running
    checked, t_end = 0, time.time() + max_seconds
    try:
        while time.time() < t_end:
            gen = get_session()
            session = next(gen)
            try:
                if not monitor.is_enabled(session):
                    break
                checked += monitor.tick(session, graph=True)["scanned"]
            except Exception:  # noqa: BLE001 — a failed tick must not kill the monitor
                log.exception("scheme monitor tick failed")
                session.rollback()
            finally:
                gen.close()
            r.expire(MONITOR_LOCK, 30)
            time.sleep(pause)
    finally:
        r.delete(MONITOR_LOCK)
    return checked
