from app.services.fingerprint import compare
from app.services.pipeline import (
    extract_features,
    fingerprint_from_processed,
    gambling_from_tags,
)

_PROCESS_OUT = {"content_id", "sha256", "features"}


class FakeEmbedder:
    def __init__(self, vec):
        self.vec = vec
        self.calls = 0
        self.last = None

    def embed_text(self, texts):
        self.calls += 1
        self.last = texts
        return [self.vec for _ in texts]


class FakeTranscriber:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def transcribe(self, audio, *, filename="audio.mp3"):
        self.calls += 1
        return self.text


class FakeVisionTagger:
    def __init__(self, tags):
        self.tags = tags
        self.calls = 0

    def tag(self, image, *, prompt=None):
        self.calls += 1
        return self.tags


class FakeOCR:
    def __init__(self, text):
        self.text = text

    def ocr(self, image):
        return self.text


def _collected(cid, text, **ids):
    return {"content_id": cid, "source": "youtube", "sha256": "a" * 64,
            "raw_key": "k", "author": "@a", "text": text, **ids}


def test_extract_features_embeds_text_and_meets_contract():
    emb = FakeEmbedder([0.1, 0.2, 0.3])
    out = extract_features(emb, _collected("c1", "вложи 50 тысяч", wallets=["USDT-X"]))
    assert _PROCESS_OUT <= out.keys()
    assert out["features"]["text"] == [0.1, 0.2, 0.3]
    assert out["wallets"] == ["USDT-X"]
    assert emb.calls == 1


def test_no_text_skips_embedding():
    emb = FakeEmbedder([1.0])
    out = extract_features(emb, _collected("c2", ""))
    assert out["features"]["text"] == []
    assert emb.calls == 0


def test_audio_is_transcribed_and_embedded():
    emb, tr = FakeEmbedder([0.5]), FakeTranscriber("вложи 50 тысяч и получай 10")
    collected = {"content_id": "c3", "source": "telegram", "sha256": "b" * 64,
                 "raw_key": "k", "author": "@a", "audio": b"\x00\x01"}
    out = extract_features(emb, collected, transcriber=tr)
    assert tr.calls == 1
    assert "вложи 50 тысяч" in out["text"]
    assert emb.last == [out["text"]]        # the transcript was what got embedded
    assert out["features"]["text"] == [0.5]


def test_caption_and_audio_are_combined():
    emb, tr = FakeEmbedder([1.0]), FakeTranscriber("аудио-текст")
    collected = {"content_id": "c4", "source": "telegram", "sha256": "c" * 64,
                 "raw_key": "k", "author": "@a", "text": "описание", "audio": b"x"}
    out = extract_features(emb, collected, transcriber=tr)
    assert "описание" in out["text"] and "аудио-текст" in out["text"]


def test_transcript_and_ocr_retained_separately_and_custody_passed_through():
    emb, tr = FakeEmbedder([1.0]), FakeTranscriber("речь из ролика")
    collected = {"content_id": "c4b", "source": "youtube", "sha256": "c" * 64,
                 "raw_key": "youtube/k.mp4", "evidence_key": "youtube/k.mp4",
                 "size": 123, "content_type": "video/mp4",
                 "author": "@a", "text": "подпись", "audio": b"x",
                 "image": b"f", "images": [b"f"]}
    out = extract_features(emb, collected, transcriber=tr, ocr=FakeOCR("ГАРАНТ 30%"))
    # speech and on-screen text are retained as distinct evidence fields...
    assert out["transcript"] == "речь из ролика"
    assert out["ocr_text"] == "ГАРАНТ 30%"
    # ...while the merged text (for embedding/NLP) still contains all three sources
    assert all(s in out["text"] for s in ("подпись", "речь из ролика", "ГАРАНТ 30%"))
    # chain-of-custody fields pass through for the Evidence row
    assert out["evidence_key"] == "youtube/k.mp4" and out["size"] == 123
    assert out["content_type"] == "video/mp4"


def test_no_transcriber_leaves_audio_untranscribed():
    emb = FakeEmbedder([1.0])
    out = extract_features(emb, {"content_id": "c5", "source": "x", "sha256": "d" * 64,
                                 "raw_key": "k", "author": "@a", "audio": b"x"})
    assert out["text"] == "" and emb.calls == 0


def test_gambling_tags_map_to_factor():
    assert gambling_from_tags(["slot machine", "luxury car"]) is True
    assert gambling_from_tags(["Casino"]) is True            # case-insensitive
    assert gambling_from_tags(["car", "money"]) is False


def test_image_is_tagged_and_sets_gambling_flag():
    emb, vt = FakeEmbedder([0.1]), FakeVisionTagger(["casino", "money"])
    collected = {"content_id": "c6", "source": "tiktok", "sha256": "e" * 64,
                 "raw_key": "k", "author": "@a", "text": "x", "image": b"\xff\xd8"}
    out = extract_features(emb, collected, vision=vt)
    assert vt.calls == 1
    assert out["tags"] == ["casino", "money"]
    assert out["gambling_content"] is True


def test_no_image_no_tags():
    out = extract_features(FakeEmbedder([1.0]), {
        "content_id": "c7", "source": "x", "sha256": "f" * 64, "raw_key": "k",
        "author": "@a", "text": "hi"})
    assert out["tags"] == [] and out["gambling_content"] is False


def test_ocr_folds_onscreen_text_into_analysis():
    emb = FakeEmbedder([0.2])
    collected = {"content_id": "c8", "source": "youtube", "sha256": "g" * 64, "raw_key": "k",
                 "author": "@a", "text": "описание", "image": b"\xff\xd8"}
    out = extract_features(emb, collected, ocr=FakeOCR("ГАРАНТИРУЮ 30% в день @scam"))
    assert "описание" in out["text"] and "ГАРАНТИРУЮ 30%" in out["text"]
    assert emb.last == [out["text"]]              # on-screen text was embedded too


def test_registry_verified_license_overrides_text(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "licensed_registry", ["legit-broker.kz"])
    emb = FakeEmbedder([1.0])
    base = {"content_id": "c9", "source": "x", "sha256": "h" * 64, "raw_key": "k", "author": "@a", "text": "t"}

    licensed = extract_features(emb, {**base, "domains": ["legit-broker.kz"]})
    assert licensed["claims"]["has_license"] is True

    unlicensed = extract_features(emb, {**base, "domains": ["scam-casino.io"]})
    assert unlicensed["claims"]["has_license"] is False


def test_fingerprint_assembled_from_processed():
    emb = FakeEmbedder([1.0, 0.0, 0.0])
    proc = extract_features(emb, _collected("c1", "x", telegram=["fastmoney"]))
    fp = fingerprint_from_processed(proc)
    assert fp.content_id == "c1"
    assert fp.vectors["text"] == [1.0, 0.0, 0.0]
    assert "tg:fastmoney" in fp.hard_identifiers()


def test_similar_text_and_shared_wallet_match_strongly():
    emb = FakeEmbedder([1.0, 0.0, 0.0])
    a = fingerprint_from_processed(extract_features(emb, _collected("c1", "scam", wallets=["USDT-X"])))
    b = fingerprint_from_processed(extract_features(emb, _collected("c2", "scam", wallets=["USDT-X"])))
    m = compare(a, b)
    # text weight is 0.5 of the soft score (visual/audio absent) -> identical text => 0.5
    assert m.soft_similarity == 0.5
    assert "wallet:usdt-x" in m.shared_identifiers
    assert m.likely_same_scheme is True      # shared wallet is decisive regardless
