from unittest.mock import MagicMock

from app.core.startup import initialize_stores


def test_initializes_all_three_stores():
    ev, fp, gb = MagicMock(), MagicMock(), MagicMock()
    initialize_stores(ev, fp, gb)
    ev.ensure_buckets.assert_called_once()
    fp.init_collection.assert_called_once()
    gb.init_schema.assert_called_once()


def test_is_idempotent_on_repeat_boot():
    # Underlying calls are idempotent; running twice must not raise.
    ev, fp, gb = MagicMock(), MagicMock(), MagicMock()
    initialize_stores(ev, fp, gb)
    initialize_stores(ev, fp, gb)
    assert ev.ensure_buckets.call_count == 2
    assert fp.init_collection.call_count == 2
    assert gb.init_schema.call_count == 2
