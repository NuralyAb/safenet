from app.services.risk_engine import FactorSignal, ThreatLevel, assess


def test_score_is_weighted_sum_and_traceable():
    signals = [
        FactorSignal("financial_promises", 1.0, ["ev-1"], "обещание гарантированной прибыли"),
        FactorSignal("referral_structure", 1.0, ["ev-2"], "реферальная система"),
        FactorSignal("known_scheme_repetition", 0.85, ["ev-3"], "повтор схемы из 17 аккаунтов"),
        FactorSignal("suspicious_links", 0.6, ["ev-4"]),
        FactorSignal("gambling_content", 0.0, []),
        FactorSignal("infra_anonymity", 1.0, ["ev-5"], "анонимные Telegram группы"),
    ]
    a = assess(signals)
    # 25 + 20 + 17 + 9 + 0 + 10 = 81
    assert a.score == 81
    assert a.threat_level == ThreatLevel.HIGH
    # every contributing factor carries its evidence -> defensible
    top = a.breakdown[0]
    assert top["factor"] == "financial_promises"
    assert top["evidence_ids"] == ["ev-1"]


def test_score_clamps_at_100():
    signals = [FactorSignal(f, 1.0, ["ev"]) for f in
               ("financial_promises", "referral_structure", "known_scheme_repetition",
                "suspicious_links", "gambling_content", "infra_anonymity")]
    assert assess(signals).score == 100
    assert assess(signals).threat_level == ThreatLevel.HIGH      # SafeNet KZ: 3 levels only


def test_empty_signals_is_low():
    a = assess([])
    assert a.score == 0
    assert a.threat_level == ThreatLevel.LOW
