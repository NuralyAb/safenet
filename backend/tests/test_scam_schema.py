from fastapi.testclient import TestClient

from app.main import app
from app.services.clustering import (
    rebuild_scam_schemas,
    scam_schema_id,
    schema_assignments,
)
from app.services.fingerprint import Fingerprint


def test_schema_id_is_deterministic_and_order_independent():
    assert scam_schema_id(["c1", "c2"]) == scam_schema_id(["c2", "c1"])
    assert scam_schema_id(["c1", "c2"]) != scam_schema_id(["c1", "c3"])
    assert scam_schema_id(["c1"]).startswith("schema-")


def test_assignments_keep_real_schemes_only():
    clusters = [["a", "b", "c"], ["d"], ["e", "f"]]
    out = schema_assignments(clusters, min_size=2)
    assert [s["size"] for s in out] == [3, 2]        # singleton dropped, sorted by size
    assert out[0]["members"] == ["a", "b", "c"]
    assert all(s["schema_id"].startswith("schema-") for s in out)


# --- orchestrator with fakes (no Qdrant/Neo4j) -------------------------------
class FakeStore:
    def __init__(self, fps):
        self._fps = fps

    def scroll_all(self, limit=10000):
        return self._fps


class FakeGraph:
    def __init__(self):
        self.written = None

    def write_scam_schemas(self, assignments):
        self.written = assignments
        return assignments


def test_rebuild_clusters_and_writes_to_graph():
    fps = [
        Fingerprint("c1", "@a", {}, wallets=["W"]),
        Fingerprint("c2", "@b", {}, wallets=["W"]),   # same wallet -> one scheme
        Fingerprint("c3", "@c", {}, wallets=["Z"]),   # singleton -> excluded
    ]
    graph = FakeGraph()
    out = rebuild_scam_schemas(FakeStore(fps), graph)
    assert len(out) == 1 and out[0]["members"] == ["c1", "c2"]
    assert graph.written == out                       # persisted to the graph


def test_rebuild_endpoint_requires_supervisor():
    client = TestClient(app)
    assert client.post("/api/v1/graph/schemas/rebuild").status_code == 401  # no token
