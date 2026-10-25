"""Auto-collection is manual: off by default, «Остановить» cancels queued sweep work."""
import pytest
from celery.exceptions import Ignore

from app.db import settings_repo as cfg
from app.services import runtime_config as rc
from app.workers import tasks


def test_auto_collection_is_off_by_default():
    assert cfg.SWEEP_ENABLED_DEFAULT is False
    assert rc.default("watchlist_enabled") is False


def test_stopped_sweep_work_is_dropped_before_paid_stages(monkeypatch):
    monkeypatch.setattr(tasks, "sweep_stopped", lambda: True)
    with pytest.raises(Ignore):
        tasks._cancel_if_sweep_stopped(tasks.SWEEP_ORIGIN, "process")
    tasks._cancel_if_sweep_stopped(None, "process")          # manual collection keeps running
    tasks._cancel_if_sweep_stopped("manual", "process")


def test_running_sweep_work_continues(monkeypatch):
    monkeypatch.setattr(tasks, "sweep_stopped", lambda: False)
    tasks._cancel_if_sweep_stopped(tasks.SWEEP_ORIGIN, "process")   # no exception


def test_fanout_tags_items_with_origin(monkeypatch):
    sent = []

    class _Sig:
        def __init__(self, item):
            self.item = item

        def apply_async(self):
            sent.append(self.item)

    monkeypatch.setattr(tasks, "sweep_stopped", lambda: False)
    monkeypatch.setattr(tasks, "chain", lambda first, *_: _Sig(first.args[0]))
    assert tasks.fanout_items.run([{"content_id": "c1"}], tasks.SWEEP_ORIGIN) == 1
    assert sent[0]["origin"] == tasks.SWEEP_ORIGIN
