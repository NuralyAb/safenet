from dataclasses import dataclass

from app.services import risk_engine
from app.services.investigation import (
    network_summary_from_row,
    profile_from_content,
    risk_signals,
    scheme_matches_from_rows,
)
from app.workflows.types import NetworkSummary, ProfileData, SchemeMatch


@dataclass
class _Row:
    id: str
    promises_returns: bool = False
    has_referral: bool = False
    has_license: bool = False
    gambling_content: bool = False


def test_profile_from_content_collects_ids():
    p = profile_from_content([_Row("c1"), _Row("c2")], "@money_fast")
    assert p.target == "@money_fast"
    assert p.content_ids == ["c1", "c2"]


def test_profile_aggregates_nlp_claim_flags():
    rows = [_Row("c1", promises_returns=True),
            _Row("c2", has_referral=True, gambling_content=True)]
    p = profile_from_content(rows, "@x")
    assert p.promises_returns and p.has_referral and p.gambling_content
    assert p.has_license is False
    # claims now drive real score factors
    a = risk_engine.assess(risk_signals(p, matches=[], network=NetworkSummary()))
    # financial 25 + referral 20 + gambling 10 + no-license 10 = 65
    assert a.score == 65


def test_scheme_matches_from_graph_rows():
    rows = [{"author": "@invest_money", "shared": ["wallet:USDT-X", "tg:fastmoney"]}]
    matches = scheme_matches_from_rows(rows)
    assert matches[0].author == "@invest_money"
    assert "tg:fastmoney" in matches[0].shared_identifiers
    assert matches[0].score == 1.0


def test_network_summary_defaults_on_empty_row():
    n = network_summary_from_row({})
    assert (n.related_objects, n.accounts, n.wallets) == (0, 0, 0)


def test_network_summary_maps_counts():
    n = network_summary_from_row(
        {"related": 12, "accounts": 3, "telegram": 1, "wallets": 2, "websites": 1}
    )
    assert n.related_objects == 12 and n.accounts == 3 and n.wallets == 2


def test_risk_signals_are_data_driven_and_scored():
    profile = ProfileData(target="@x")                       # no NLP flags yet
    matches = [SchemeMatch("@a", "@a", 1.0, ["wallet:USDT-X"])] * 5
    network = NetworkSummary(related_objects=15)
    signals = risk_signals(profile, matches, network)

    by = {s.factor: s for s in signals}
    assert by["known_scheme_repetition"].strength == 0.5   # 5/10
    assert by["suspicious_links"].strength == 0.5          # 15/30
    assert by["infra_anonymity"].strength == 1.0           # no license

    # deterministic score: 20*0.5 + 15*0.5 + 10*1.0 = 27.5 -> 28 (LOW, <40)
    a = risk_engine.assess(signals)
    assert a.score == 28
    assert a.threat_level is risk_engine.ThreatLevel.LOW
