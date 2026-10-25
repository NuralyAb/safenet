"""Celery app for the collection + multimodal processing pipeline.

Queues:
  collect    — per-source collectors fetch content + store original to WORM
  process    — STT / vision / OCR / NLP / biometrics (GPU workers)
  fingerprint— build composite fingerprint, upsert to Qdrant, update Fraud Graph

At <=10K videos/day this throughput is comfortable without Kafka/streaming.
Chain stages with Celery canvas; the AI Investigator runs on Temporal, not here.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "afm", broker=settings.redis_url, backend=settings.redis_url,
    include=["app.workers.tasks"],   # register tasks on the worker (else "unregistered task")
)
celery_app.conf.task_routes = {
    "app.workers.tasks.collect_*": {"queue": "collect"},
    "app.workers.tasks.discover_*": {"queue": "collect"},
    "app.workers.tasks.fanout_items": {"queue": "collect"},
    "app.workers.tasks.sweep_watchlist": {"queue": "collect"},
    "app.workers.tasks.process_*": {"queue": "process"},
    "app.workers.tasks.fingerprint_*": {"queue": "fingerprint"},
    "app.workers.tasks.score_*": {"queue": "fingerprint"},
}
celery_app.conf.task_acks_late = True          # don't lose work on worker crash
celery_app.conf.worker_prefetch_multiplier = 1  # GPU tasks are long; fair dispatch

# Continuous monitoring: beat ticks every 60s; sweep_watchlist self-gates on the
# UI-configurable interval (app_setting) so the period is changeable without a
# restart. The env value is only the initial default for that interval.
celery_app.conf.beat_schedule = {
    "sweep-watchlist": {
        "task": "app.workers.tasks.sweep_watchlist",
        "schedule": 60.0,
    },
    # «Мониторинг схем»: keeps the monitor loop alive while it is on (no-op when off)
    "safenet-monitor": {
        "task": "app.workers.tasks.collect_safenet_monitor",
        "schedule": 30.0,
    },
}
