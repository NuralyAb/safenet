from app.services.claims import CLAIM_KEYS, aggregate_claims, extract_claims, parse_claims


class FakeLLM:
    def __init__(self, out="", fail=False):
        self.out, self.fail, self.seen = out, fail, None

    def complete(self, system, user):
        if self.fail:
            raise RuntimeError("down")
        self.seen = user
        return self.out


def test_parse_plain_json():
    flags = parse_claims('{"promises_returns": true, "has_referral": true, '
                         '"has_license": false, "gambling_content": false}')
    assert flags["promises_returns"] and flags["has_referral"]
    assert not flags["has_license"]


def test_parse_strips_code_fences_and_prose():
    raw = "Вот результат:\n```json\n{\"promises_returns\": true}\n```"
    assert parse_claims(raw)["promises_returns"] is True
    assert parse_claims(raw)["has_referral"] is False   # missing -> False


def test_parse_garbage_is_all_false():
    for raw in ("", "not json", "{broken", "[]"):
        assert parse_claims(raw) == {k: False for k in CLAIM_KEYS}


def test_extract_claims_uses_llm_and_passes_text():
    llm = FakeLLM(out='{"promises_returns": true, "gambling_content": true}')
    flags = extract_claims(llm, "вложи и получай, казино")
    assert flags["promises_returns"] and flags["gambling_content"]
    assert "вложи" in llm.seen


def test_extract_claims_failsafe_on_error_or_empty():
    assert extract_claims(FakeLLM(fail=True), "text") == {k: False for k in CLAIM_KEYS}
    assert extract_claims(FakeLLM(out="{}"), "") == {k: False for k in CLAIM_KEYS}  # empty text


def test_aggregate_ors_across_content():
    items = [
        {"promises_returns": True, "has_referral": False},
        {"promises_returns": False, "has_referral": True, "gambling_content": True},
    ]
    agg = aggregate_claims(items)
    assert agg["promises_returns"] and agg["has_referral"] and agg["gambling_content"]
    assert agg["has_license"] is False
