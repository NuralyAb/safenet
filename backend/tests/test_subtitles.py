from app.services.subtitles import clean_subtitles

VTT = """WEBVTT
Kind: captions
Language: ru

00:00:01.000 --> 00:00:03.000
Вложи 100 долларов

00:00:03.000 --> 00:00:05.000
<c>и получай 30% в день</c>

00:00:05.000 --> 00:00:07.000
Вложи 100 долларов
"""


def test_clean_strips_headers_timestamps_tags():
    out = clean_subtitles(VTT)
    assert "Вложи 100 долларов" in out and "получай 30% в день" in out
    assert "WEBVTT" not in out and "-->" not in out and "<c>" not in out


def test_clean_dedupes_repeated_cues():
    out = clean_subtitles(VTT)
    assert out.split().count("Вложи") == 1     # repeated line collapsed


def test_empty_is_safe():
    assert clean_subtitles("") == ""
