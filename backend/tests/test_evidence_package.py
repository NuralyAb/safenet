from fastapi.testclient import TestClient

from app.main import app
from app.services.evidence_package import build_package, package_hash, render_markdown

REPORT = {
    "target": "@money_fast",
    "category": "Investment Fraud",
    "risk": {
        "score": 84, "threat_level": "HIGH", "recommendation": "Передать на проверку",
        "breakdown": [
            {"factor": "financial_promises", "contribution": 25,
             "evidence_ids": ["ev-1"], "note": "обещание прибыли"},
        ],
    },
    "findings": ["обещание прибыли"],
    "scheme_matches": 3,
    "network": {"related_objects": 42, "accounts": 14, "wallets": 2},
    "narrative": "Объект демонстрирует признаки инвестиционного мошенничества.",
}
EVIDENCE = [
    {"sha256": "a" * 64, "evidence_key": "youtube/aa/aa/" + "a" * 64,
     "collected_at": "2026-06-23T10:00:00Z", "source": "youtube", "url": "https://y/1"},
]

ARGS = {"generated_at": "2026-06-23T12:00:00Z", "generated_by": "analyst-1"}


def test_package_binds_ai_output_to_chain_of_custody():
    p = build_package(REPORT, EVIDENCE, **ARGS)
    assert p["object"] == "@money_fast"
    assert p["risk"]["score"] == 84
    assert p["factors"][0]["evidence_ids"] == ["ev-1"]      # explainable -> defensible
    assert p["evidence"][0]["sha256"] == "a" * 64           # chain of custody included
    assert "manifest_sha256" in p


def test_manifest_hash_is_tamper_evident():
    p = build_package(REPORT, EVIDENCE, **ARGS)
    # recomputing the manifest over the untouched body matches
    assert package_hash(p) == p["manifest_sha256"]
    # editing any field breaks it
    tampered = dict(p, narrative="(подделано)")
    assert package_hash(tampered) != tampered["manifest_sha256"]


def test_markdown_renders_key_sections():
    md = render_markdown(build_package(REPORT, EVIDENCE, **ARGS))
    assert "Аналитическая справка" in md
    assert "84/100" in md
    assert "ev-1" in md and "a" * 64 in md
    assert "Хеш-манифест" in md


def test_endpoint_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/investigations/inv-x/evidence-package").status_code == 401
