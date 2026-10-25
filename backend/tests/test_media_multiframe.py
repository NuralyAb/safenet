from app.services import media
from app.services.media import enrich_with_media, extract_frames, frame_offsets


def test_frame_offsets_spread_across_timeline():
    assert frame_offsets(4) == [1.0, 4.0, 7.0, 10.0]      # start 1.0, step 3.0
    assert frame_offsets(1) == [1.0]
    assert frame_offsets(0) == [1.0]                      # at least one


def test_extract_frames_collects_one_per_offset(monkeypatch):
    def fake_run(cmd):
        with open(cmd[-1], "wb") as fh:                   # cmd[-1] is the dst path
            fh.write(b"FRM")
    monkeypatch.setattr(media, "_run", fake_run)
    frames = extract_frames(b"VIDEO", count=3)
    assert frames == [b"FRM", b"FRM", b"FRM"]


def test_extract_frames_skips_failed_offset(monkeypatch):
    n = {"i": 0}

    def fake_run(cmd):
        n["i"] += 1
        if n["i"] == 2:                                   # second offset is past the clip end
            raise RuntimeError("past end")
        with open(cmd[-1], "wb") as fh:
            fh.write(b"OK")
    monkeypatch.setattr(media, "_run", fake_run)
    frames = extract_frames(b"V", count=3)
    assert frames == [b"OK", b"OK"]                       # failed offset dropped, others kept


def test_enrich_multiframe_populates_images(monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(media, "extract_audio", lambda b: b"AUDIO")
    monkeypatch.setattr(media, "extract_frames", lambda b, count=4: [b"F1", b"F2"])
    out = enrich_with_media({"raw_key": "k"}, lambda key: b"VIDEO", frames=4)
    assert out["images"] == [b"F1", b"F2"]
    assert out["image"] == b"F1"                          # first frame for single-frame consumers
    assert out["audio"] == b"AUDIO"


def test_enrich_single_frame_default_unchanged(monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(media, "extract_audio", lambda b: b"AUDIO")
    monkeypatch.setattr(media, "extract_frame", lambda b, at=1.0: b"FRAME")
    out = enrich_with_media({"raw_key": "k", "audio": None, "image": None}, lambda key: b"V")
    assert out["image"] == b"FRAME" and "images" not in out   # frames=1 keeps old behaviour
