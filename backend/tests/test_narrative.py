from app.services.investigation import (
    compose_narrative_text,
    fallback_narrative,
    narrative_prompt,
)
from app.workflows.types import NetworkSummary, ProfileData, RiskResult

PROFILE = ProfileData(target="@money_fast")
RISK = RiskResult(
    score=84, threat_level="HIGH",
    breakdown=[{"factor": "infra_anonymity", "note": "отсутствие лицензии"},
               {"factor": "known_scheme_repetition", "note": "совпадений со схемами: 3"}],
    recommendation="Передать на ручную проверку",
)
NETWORK = NetworkSummary(related_objects=42, accounts=14, wallets=2)


class FakeLLM:
    def __init__(self, out="", fail=False):
        self.out, self.fail, self.seen = out, fail, None

    def complete(self, system, user):
        if self.fail:
            raise RuntimeError("LLM down")
        self.seen = (system, user)
        return self.out


def test_prompt_carries_facts_and_forbids_scoring():
    system, user = narrative_prompt(PROFILE, RISK, 3, NETWORK)
    assert "НЕ оценивай" in system or "не оцен" in system.lower()
    assert "@money_fast" in user and '"risk_score": 84' in user
    assert "отсутствие лицензии" in user            # findings travel to the LLM


def test_uses_llm_output_when_available():
    llm = FakeLLM(out="Связный отчёт по фактам.")
    assert compose_narrative_text(llm, PROFILE, RISK, 3, NETWORK) == "Связный отчёт по фактам."
    # the real score went INTO the prompt (LLM narrates it, doesn't invent it)
    assert '"risk_score": 84' in llm.seen[1]


def test_falls_back_on_llm_failure():
    text = compose_narrative_text(FakeLLM(fail=True), PROFILE, RISK, 3, NETWORK)
    assert text == fallback_narrative(PROFILE, RISK, 3, NETWORK)
    assert "84/100" in text and "@money_fast" in text


def test_empty_llm_output_falls_back():
    text = compose_narrative_text(FakeLLM(out="   "), PROFILE, RISK, 3, NETWORK)
    assert "84/100" in text
