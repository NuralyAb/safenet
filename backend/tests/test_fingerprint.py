from app.services.fingerprint import Fingerprint, compare, _point_id


def test_shared_hard_identifier_means_same_scheme():
    a = Fingerprint("c1", "@crypto_profit", {"text": [1, 0, 0]}, telegram=["FastMoney"])
    b = Fingerprint("c2", "@wealth2026", {"text": [0, 1, 0]}, telegram=["fastmoney"])
    m = compare(a, b)
    # different soft vectors, but a shared (case-insensitive) telegram handle is decisive
    assert m.shared_identifiers == ["tg:fastmoney"]
    assert m.likely_same_scheme is True
    assert m.content_id == "c2"


def test_soft_similarity_alone_can_flag_same_scheme():
    a = Fingerprint("c1", "@a", {"text": [1, 0, 0], "visual": [1, 0, 0], "audio": [1, 0, 0]})
    b = Fingerprint("c2", "@b", {"text": [1, 0, 0], "visual": [1, 0, 0], "audio": [1, 0, 0]})
    m = compare(a, b)
    assert m.soft_similarity == 1.0
    assert m.likely_same_scheme is True


def test_unrelated_content_is_not_a_match():
    a = Fingerprint("c1", "@a", {"text": [1, 0, 0]}, wallets=["0xAAA"])
    b = Fingerprint("c2", "@b", {"text": [0, 1, 0]}, wallets=["0xBBB"])
    m = compare(a, b)
    assert m.shared_identifiers == []
    assert m.likely_same_scheme is False


def test_point_id_is_stable_and_unique():
    assert _point_id("c1") == _point_id("c1")
    assert _point_id("c1") != _point_id("c2")
