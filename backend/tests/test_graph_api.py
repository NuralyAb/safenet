from fastapi.testclient import TestClient

from app.main import app
from app.services.investigation import subgraph_from_edge_rows

ROWS = [
    {"source": "@fast_profit", "target": "wallet:USDT-X", "label": "MENTIONS",
     "confidence": 1.0, "evidence_id": "seed",
     "source_labels": ["Account"], "target_labels": ["Infrastructure"]},
    {"source": "@invest_money", "target": "wallet:USDT-X", "label": "MENTIONS",
     "confidence": 1.0, "evidence_id": "seed",
     "source_labels": ["Account"], "target_labels": ["Infrastructure"]},
    {"source": "@fast_profit", "target": "@invest_money", "label": "SAME_PERSON",
     "confidence": 0.82, "evidence_id": "seed", "confirmed": False,
     "source_labels": ["Account"], "target_labels": ["Account"]},
]


def test_subgraph_dedupes_nodes_and_types_them():
    g = subgraph_from_edge_rows(ROWS)
    nodes = {n["id"]: n["type"] for n in g["nodes"]}
    assert nodes["@fast_profit"] == "account"
    assert nodes["wallet:USDT-X"] == "wallet"   # id-prefix derives the type
    assert len(g["nodes"]) == 3                  # wallet appears once despite two edges


def test_unconfirmed_same_person_becomes_candidate_label():
    g = subgraph_from_edge_rows(ROWS)
    sp = [e for e in g["edges"] if e["source"] == "@fast_profit" and e["target"] == "@invest_money"]
    assert sp[0]["label"] == "SAME_PERSON?"      # dashed candidate on the dashboard


def test_normal_edges_are_not_marked_candidate():
    g = subgraph_from_edge_rows(ROWS)
    mentions = [e for e in g["edges"] if e["label"] == "MENTIONS"]
    assert len(mentions) == 2
    assert all("?" not in e["label"] for e in mentions)


def test_graph_endpoint_requires_auth():
    # RBAC guard runs before Neo4j is touched -> 401 without a token.
    client = TestClient(app)   # no `with` -> no lifespan/startup
    assert client.get("/api/v1/graph/@fast_profit").status_code == 401
