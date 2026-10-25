"""Runtime config registry: validation + coercion (no DB needed for these)."""
import pytest

from app.services import runtime_config as rc


def test_validate_coerces_and_range_checks():
    assert rc.validate("collect_video_limit", "7") == "7"          # str -> int
    assert rc.validate("ai_retry_base_seconds", 2) == "2.0"        # int -> float
    assert rc.validate("watchlist_enabled", True) == "true"        # bool
    assert rc.validate("ai_provider", "anthropic") == "anthropic"  # enum ok


def test_validate_rejects_out_of_range():
    with pytest.raises(ValueError):
        rc.validate("collect_video_limit", 0)        # below min=1
    with pytest.raises(ValueError):
        rc.validate("ai_max_retries", 99)            # above max=10


def test_validate_rejects_bad_enum_and_unknown_key():
    with pytest.raises(ValueError):
        rc.validate("ai_provider", "gemini")         # not in options
    with pytest.raises(rc.UnknownSetting):
        rc.validate("nope", 1)


def test_registry_covers_expected_knobs():
    keys = {s.key for s in rc.REGISTRY}
    assert {"collect_video_limit", "ai_provider", "ai_max_retries",
            "ai_retry_base_seconds", "watchlist_sweep_seconds"} <= keys
