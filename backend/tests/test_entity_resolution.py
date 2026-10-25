from app.services.entity_resolution import (
    AUTO_CONFIRM_FORBIDDEN,
    confirm,
    score_link,
)


def test_identity_is_never_auto_confirmed():
    # Invariant of the whole module: no machine-asserted identity.
    assert AUTO_CONFIRM_FORBIDDEN is True


def test_strong_candidate_still_requires_human_confirmation():
    c = score_link(
        {"face": 0.95, "voice": 0.9, "contact_overlap": 1.0},
        evidence_ids=["ev-face", "ev-voice"],
        account_a="@a",
        account_b="@b",
    )
    assert c.confidence >= 0.8
    assert c.status == "STRONG_CANDIDATE"
    assert c.confirmed is False          # high confidence is NOT confirmation


def test_confirmation_records_the_analyst():
    c = score_link({"face": 0.95, "voice": 0.9}, ["ev"], "@a", "@b")
    confirm(c, analyst_id="analyst-7")
    assert c.confirmed is True
    assert c.confirmed_by == "analyst-7"
    assert c.status == "CONFIRMED"


def test_weak_signals_are_flagged_weak():
    c = score_link({"face": 0.3}, [], "@a", "@b")
    assert c.status == "WEAK_CANDIDATE"
