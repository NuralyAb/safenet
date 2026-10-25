import pytest

from app.services import media
from app.services.media import enrich_with_media, ffmpeg_audio_cmd, ffmpeg_frame_cmd


# --- pure command builders ---------------------------------------------------
def test_audio_cmd_strips_video_to_mp3():
    cmd = ffmpeg_audio_cmd("in.mp4", "out.mp3")
    assert "-vn" in cmd and "libmp3lame" in cmd
    assert cmd[-1] == "out.mp3" and cmd[0] == "ffmpeg"


def test_frame_cmd_grabs_one_frame_at_offset():
    cmd = ffmpeg_frame_cmd("in.mp4", "f.jpg", at=2.5)
    assert "-frames:v" in cmd and "1" in cmd
    assert "2.5" in cmd and cmd[-1] == "f.jpg"


# --- enrich logic (ffmpeg + extractors monkeypatched) ------------------------
@pytest.fixture
def fake_ffmpeg(monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(media, "extract_audio", lambda b: b"AUDIO")
    monkeypatch.setattr(media, "extract_frame", lambda b, at=1.0: b"FRAME")


def test_enrich_fetches_and_extracts(fake_ffmpeg):
    calls = []
    collected = {"raw_key": "youtube/abc", "audio": None, "image": None}
    out = enrich_with_media(collected, lambda key: calls.append(key) or b"VIDEO")
    assert out["audio"] == b"AUDIO" and out["image"] == b"FRAME"
    assert calls == ["youtube/abc"]            # fetched the original once


def test_enrich_skips_when_already_present(fake_ffmpeg):
    collected = {"raw_key": "k", "audio": b"A", "image": b"I"}
    fetched = []
    out = enrich_with_media(collected, lambda key: fetched.append(key) or b"V")
    assert out is collected and fetched == []   # nothing to do


def test_enrich_noop_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_available", lambda: False)
    collected = {"raw_key": "k", "audio": None, "image": None}
    assert enrich_with_media(collected, lambda key: b"V") == collected
