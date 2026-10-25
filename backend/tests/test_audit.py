from dataclasses import replace

from app.services.audit import make_entry, verify_chain


def _chain():
    e0 = make_entry(None, "2026-06-22T10:00:00Z", "analyst-1", "login", "-")
    e1 = make_entry(e0, "2026-06-22T10:01:00Z", "analyst-1", "investigation.open", "@money_fast")
    e2 = make_entry(e1, "2026-06-22T10:02:00Z", "analyst-1", "biometric.view", "person:1")
    return [e0, e1, e2]


def test_intact_chain_verifies():
    assert verify_chain(_chain()) is True


def test_tampering_with_an_entry_breaks_the_chain():
    chain = _chain()
    # Attacker edits a past action but keeps the stored hash -> mismatch.
    chain[1] = replace(chain[1], action="investigation.cancel")
    assert verify_chain(chain) is False


def test_deleting_an_entry_breaks_the_chain():
    chain = _chain()
    del chain[1]                       # seq gap + broken prev_hash linkage
    assert verify_chain(chain) is False


def test_genesis_links_to_zero_hash():
    e0 = _chain()[0]
    assert e0.seq == 0
    assert e0.prev_hash == "0" * 64
