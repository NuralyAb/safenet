from app.services.claims import (
    CONTENT_FACT_KEYS,
    SIGNAL_KEYS,
    extract_content_facts,
    parse_content_facts,
)


class FakeLLM:
    def __init__(self, out="", fail=False):
        self.out, self.fail, self.seen = out, fail, None

    def complete(self, system, user):
        if self.fail:
            raise RuntimeError("down")
        self.seen = user
        return self.out


def test_signal_keys_are_the_two_new_patterns():
    assert SIGNAL_KEYS == ("aggressive_investment", "hidden_engagement")
    assert set(CONTENT_FACT_KEYS) >= set(SIGNAL_KEYS)


def test_parse_content_facts_includes_intensifiers():
    flags = parse_content_facts(
        '{"promises_returns": true, "aggressive_investment": true, "hidden_engagement": false}'
    )
    assert flags["promises_returns"] and flags["aggressive_investment"]
    assert flags["hidden_engagement"] is False
    assert set(flags) == set(CONTENT_FACT_KEYS)        # always the full 6 keys


def test_parse_garbage_is_all_false():
    for raw in ("", "not json", "{broken", "[]"):
        assert parse_content_facts(raw) == {k: False for k in CONTENT_FACT_KEYS}


def test_extract_content_facts_uses_llm_and_passes_text():
    llm = FakeLLM(out='{"promises_returns": true, "aggressive_investment": true}')
    flags = extract_content_facts(llm, "успей вложить, последний шанс")
    assert flags["promises_returns"] and flags["aggressive_investment"]
    assert "успей" in llm.seen


def test_extract_content_facts_failsafe():
    assert extract_content_facts(FakeLLM(fail=True), "t") == {k: False for k in CONTENT_FACT_KEYS}
    assert extract_content_facts(FakeLLM(out="{}"), "") == {k: False for k in CONTENT_FACT_KEYS}
