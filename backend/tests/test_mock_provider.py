import json

from app.core.config import settings
from app.services.ai import factory
from app.services.ai.mock_provider import MockProvider


def test_complete_extracts_facts_from_keywords():
    out = json.loads(MockProvider().complete(
        "Верни СТРОГО JSON с булевыми полями",
        "вложи и получай доход 300%, казино, реферальный бонус, срочно успей, пиши в @vip"))
    assert out["promises_returns"] and out["gambling_content"] and out["has_referral"]
    assert out["aggressive_investment"] and out["hidden_engagement"]
    assert out["has_license"] is False


def test_complete_clean_text_has_no_flags():
    out = json.loads(MockProvider().complete("JSON", "обзор книги про садоводство и природу"))
    assert not any(out.values())


def test_complete_returns_narrative_when_not_json():
    assert "mock" in MockProvider().complete("Ты аналитик, напиши отчёт по фактам", "факты").lower()


def test_embed_text_is_deterministic_and_right_dim():
    m = MockProvider()
    assert m.embed_text(["x"])[0] == m.embed_text(["x"])[0]              # deterministic
    assert len(m.embed_text(["x"])[0]) == settings.dim_text             # correct dimension
    assert m.embed_text(["x"])[0] != m.embed_text(["y"])[0]             # content-sensitive


def test_vision_ocr_transcribe_are_offline_canned():
    m = MockProvider()
    assert "casino" in m.tag(b"img")
    assert m.ocr(b"img")
    assert m.transcribe(b"audio")


def test_factory_routes_all_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "mock")
    assert isinstance(factory.get_llm(), MockProvider)
    assert isinstance(factory.get_embedder(), MockProvider)
    assert isinstance(factory.get_vision_tagger(), MockProvider)
    # OCR is a chain: on-prem Tesseract (if installed) first, the mock only as last resort
    ocr = factory.get_ocr()
    assert isinstance(ocr.engines[-1], MockProvider)
    assert all(type(e).__name__ in ("TesseractOCR", "MockProvider") for e in ocr.engines)


def test_fetch_media_mock_is_offline(monkeypatch):
    from app.services import adhoc
    from app.services import runtime_config as rc
    monkeypatch.setattr(rc, "get_value", lambda k: "mock" if k == "ai_provider" else None)
    p = adhoc.fetch_media("https://www.instagram.com/reel/X/")
    assert p["media"] is None and p["images"]            # synthetic image, no network
    assert p["reach"]["views"] > 0
    assert "казино" in p["caption"].lower()
