from app.services.claims import SIGNAL_KEYS
from app.services.pipeline import extract_features


class FakeEmbedder:
    def __init__(self):
        self.last = None

    def embed_text(self, texts):
        self.last = texts
        return [[0.1] for _ in texts]


class SeqVision:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = 0

    def tag(self, image, *, prompt=None):
        self.calls += 1
        return self.mapping.get(image, [])


class SeqOCR:
    def __init__(self, mapping):
        self.mapping = mapping

    def ocr(self, image):
        return self.mapping.get(image, "")


class FactsLLM:
    def __init__(self, out):
        self.out = out

    def complete(self, system, user):
        return self.out


def _collected(**extra):
    base = {"content_id": "c1", "sha256": "a" * 64, "source": "tiktok", "author": "@a"}
    return {**base, **extra}


def test_multiframe_unions_tags_and_folds_all_ocr():
    emb = FakeEmbedder()
    vision = SeqVision({b"F1": ["casino"], b"F2": ["money", "casino"]})
    ocr = SeqOCR({b"F1": "ВЛОЖИ", b"F2": "ГАРАНТ 30%"})
    out = extract_features(
        emb, _collected(text="подпись", images=[b"F1", b"F2"]),
        vision=vision, ocr=ocr,
    )
    assert vision.calls == 2                              # BOTH frames analysed
    assert out["tags"] == ["casino", "money"]            # union, order-preserving, deduped
    assert out["gambling_content"] is True
    assert "ВЛОЖИ" in out["text"] and "ГАРАНТ 30%" in out["text"]


def test_single_image_still_treated_as_one_frame():
    emb = FakeEmbedder()
    vision = SeqVision({b"IMG": ["casino", "money"]})
    out = extract_features(emb, _collected(text="x", image=b"IMG"), vision=vision)
    assert vision.calls == 1
    assert out["tags"] == ["casino", "money"]
    assert out["gambling_content"] is True


def test_output_always_exposes_signals_keys():
    out = extract_features(FakeEmbedder(), _collected(text=""))
    assert set(out["signals"]) == set(SIGNAL_KEYS)
    assert out["signals"]["aggressive_investment"] is False
    assert out["signals"]["hidden_engagement"] is False


def test_safenet_populates_both_claims_and_signals():
    llm = FactsLLM("[]")            # LLM finds nothing extra; deterministic rules still work
    text = "Успей! Вложи 5000 тг — через неделю получишь 10 000 тг"
    out = extract_features(FakeEmbedder(), _collected(text=text), llm=llm)
    assert out["claims"]["promises_returns"] is True
    assert out["signals"]["aggressive_investment"] is True
    assert out["signals"]["hidden_engagement"] is False
    assert any(h["signal"] == "pyramid.unrealistic_return" for h in out["safenet"]["hits"])
