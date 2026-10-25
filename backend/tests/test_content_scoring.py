from app.services import risk_engine
from app.services.content_scoring import score_content
from app.services.investigation import content_risk_signals


def _by_factor(signals):
    return {s.factor: s for s in signals}


def test_plain_promise_is_graded_lower_than_aggressive_call():
    base = {"promises_returns": True, "has_license": True}      # licensed -> infra contributes 0
    plain = _by_factor(content_risk_signals(base))
    assert plain["financial_promises"].strength == 0.6
    assert plain["infra_anonymity"].strength == 0.0

    aggressive = _by_factor(content_risk_signals({**base, "aggressive_investment": True}))
    assert aggressive["financial_promises"].strength == 1.0          # urgency intensifies


def test_hidden_engagement_intensifies_referral():
    base = {"has_referral": True, "has_license": True}
    plain = _by_factor(content_risk_signals(base))
    assert plain["referral_structure"].strength == 0.6
    hidden = _by_factor(content_risk_signals({**base, "hidden_engagement": True}))
    assert hidden["referral_structure"].strength == 1.0


def test_no_promise_means_zero_financial():
    s = _by_factor(content_risk_signals({"has_license": False}))
    assert s["financial_promises"].strength == 0.0
    assert s["referral_structure"].strength == 0.0
    assert s["infra_anonymity"].strength == 1.0                      # unlicensed


def test_evidence_ids_attach_to_every_factor():
    sigs = content_risk_signals({"promises_returns": True}, evidence_ids=["c1"])
    assert all(s.evidence_ids == ["c1"] for s in sigs)               # per-video traceability


def test_score_content_from_text_is_deterministic_and_traceable():
    text = ("Розыгрыш iPhone! Участие 1000 тг, переводите на Kaspi. "
            "Победителя выберем рандомайзером в прямом эфире. Осталось 15 номеров!")
    a = score_content(text=text, evidence_ids=["c1"])
    b = score_content(text=text, evidence_ids=["c1"])
    assert a.score == b.score == 100 and a.track == "lottery"
    assert a.threat_level is risk_engine.ThreatLevel.HIGH
    assert round(sum(x["contribution"] for x in a.breakdown)) == a.score   # every point traceable
    assert all(x["evidence_ids"] == ["c1"] for x in a.breakdown)


def test_score_content_legacy_facts_and_network():
    facts = {"promises_returns": True, "has_referral": True}          # weak signals, no text
    alone = score_content(facts)
    linked = score_content(facts, scheme_matches=5)
    # returns 40*0.6=24 + referral 20*0.8=16 = 40; 5 scheme matches -> network +10
    assert alone.score == 40 and alone.threat_level is risk_engine.ThreatLevel.MEDIUM
    assert linked.score == 50


def test_free_giveaway_is_not_flagged():
    a = score_content(text="Розыгрыш! Подпишись, поставь лайк и отметь 2 друзей. Участие бесплатное")
    assert a.threat_level is risk_engine.ThreatLevel.LOW
