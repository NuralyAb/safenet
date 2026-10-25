import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.ai.factory import get_face_embedder, get_speaker_embedder
from app.services.ai.local_provider import LocalProvider
from app.services.biometrics import biometric_signals, same_person_candidate
from app.services.entity_resolution import confirm
from app.services.pipeline import extract_features


# --- pure signals ------------------------------------------------------------
def test_signals_only_where_both_sides_present():
    s = biometric_signals(face_a=[1, 0, 0], face_b=[1, 0, 0], voice_a=[1, 0], voice_b=None)
    assert round(s["face"], 3) == 1.0
    assert "voice" not in s            # one side missing -> skipped
    assert biometric_signals() == {}


def test_strong_biometrics_are_a_candidate_not_a_confirmation():
    c = same_person_candidate(
        "@a", "@b", face_a=[1, 0, 0], face_b=[1, 0, 0], voice_a=[1, 0], voice_b=[1, 0],
        evidence_ids=["ev-face", "ev-voice"],
    )
    # face 0.4 + voice 0.3 = 0.7 -> conservative: biometrics alone are NOT "strong"
    assert round(c.confidence, 3) == 0.7
    assert c.confirmed is False        # NEVER auto-confirmed
    assert c.status == "WEAK_CANDIDATE"


def test_analyst_confirmation_is_the_only_path():
    c = same_person_candidate("@a", "@b", face_a=[1, 0], face_b=[1, 0])
    confirm(c, analyst_id="supervisor-2")
    assert c.confirmed is True and c.confirmed_by == "supervisor-2"
    assert c.status == "CONFIRMED"


# --- biometrics are self-hosted only -----------------------------------------
def test_biometric_embedders_are_local_only_and_need_gpu():
    assert isinstance(get_face_embedder(), LocalProvider)
    assert isinstance(get_speaker_embedder(), LocalProvider)
    with pytest.raises(NotImplementedError):
        get_face_embedder().embed_face(b"\xff\xd8")


# --- pipeline extraction (best-effort) ---------------------------------------
class FakeTextEmbedder:
    def embed_text(self, texts):
        return [[0.0] for _ in texts]


class FakeFaceEmbedder:
    def embed_face(self, image):
        return [1.0, 0.0, 0.0]


class RaisingFaceEmbedder:
    def embed_face(self, image):
        raise NotImplementedError("no GPU")


def _collected():
    return {"content_id": "c1", "source": "youtube", "sha256": "a" * 64,
            "raw_key": "k", "author": "@a", "text": "x", "image": b"\xff\xd8"}


def test_pipeline_extracts_face_embedding_when_available():
    out = extract_features(FakeTextEmbedder(), _collected(), face_embedder=FakeFaceEmbedder())
    assert out["biometric"]["face"] == [1.0, 0.0, 0.0]


def test_pipeline_best_effort_when_biometrics_unavailable():
    out = extract_features(FakeTextEmbedder(), _collected(), face_embedder=RaisingFaceEmbedder())
    assert out["biometric"] == {}      # local model raised -> no crash, just skipped


def test_confirm_same_person_endpoint_requires_supervisor():
    client = TestClient(app)
    r = client.post("/api/v1/graph/same-person",
                    json={"account_a": "@a", "account_b": "@b"})
    assert r.status_code == 401        # no token; RBAC before any graph write
