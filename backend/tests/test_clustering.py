from app.services.clustering import cluster_fingerprints
from app.services.fingerprint import Fingerprint


def _fp(cid, vec=None, **ids):
    return Fingerprint(content_id=cid, author=cid, vectors={"text": vec} if vec else {}, **ids)


def test_shared_wallet_clusters_accounts():
    fps = [
        _fp("c1", wallets=["USDT-X"]),
        _fp("c2", wallets=["USDT-X"]),      # same wallet -> same scheme as c1
        _fp("c3", wallets=["OTHER"]),       # unrelated
    ]
    clusters = cluster_fingerprints(fps)
    assert ["c1", "c2"] in clusters
    assert ["c3"] in clusters
    assert len(clusters) == 2


def test_transitive_linking_via_chain():
    # c1~c2 (wallet A), c2~c3 (telegram T) -> all one cluster transitively
    fps = [
        _fp("c1", wallets=["A"]),
        _fp("c2", wallets=["A"], telegram=["t"]),
        _fp("c3", telegram=["t"]),
    ]
    assert cluster_fingerprints(fps)[0] == ["c1", "c2", "c3"]


def test_soft_similarity_clusters_without_shared_identifiers():
    fps = [
        _fp("c1", vec=[1.0, 0.0, 0.0]),
        _fp("c2", vec=[1.0, 0.0, 0.0]),     # identical text
    ]
    # text-only soft max is 0.5 (< default 0.85) -> not clustered by default...
    assert cluster_fingerprints(fps) == [["c1"], ["c2"]]
    # ...but a lower threshold groups them
    assert cluster_fingerprints(fps, threshold=0.5)[0] == ["c1", "c2"]


def test_largest_cluster_first():
    fps = [_fp("a", wallets=["W"]), _fp("b", wallets=["W"]),
           _fp("c", wallets=["W"]), _fp("d", wallets=["Z"])]
    clusters = cluster_fingerprints(fps)
    assert clusters[0] == ["a", "b", "c"] and len(clusters[0]) == 3
