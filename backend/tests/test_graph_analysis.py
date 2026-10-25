from fastapi.testclient import TestClient

from app.main import app
from app.services.graph_builder import communities_from_rows, ringleaders_from_rows


def test_communities_grouped_and_sorted_by_size():
    rows = [
        {"name": "@a", "community": 1}, {"name": "@b", "community": 1},
        {"name": "wallet:X", "community": 1}, {"name": "@c", "community": 2},
    ]
    out = communities_from_rows(rows)
    assert out[0]["size"] == 3 and out[0]["community_id"] == 1
    assert out[0]["members"] == ["@a", "@b", "wallet:X"]
    assert out[1]["size"] == 1


def test_ringleaders_sorted_desc_and_capped():
    rows = [{"name": "@a", "score": 2.0}, {"name": "wallet:X", "score": 9.5},
            {"name": "@b", "score": 5.0}]
    out = ringleaders_from_rows(rows, top=2)
    assert [r["id"] for r in out] == ["wallet:X", "@b"]   # shared wallet brokers most
    assert len(out) == 2


def test_empty_inputs():
    assert communities_from_rows([]) == []
    assert ringleaders_from_rows([]) == []


def test_insights_route_is_not_shadowed_by_seed_and_requires_auth():
    # /insights must resolve to its own handler (not /{seed}) and enforce RBAC.
    client = TestClient(app)
    assert client.get("/api/v1/graph/insights").status_code == 401   # not 404/422
