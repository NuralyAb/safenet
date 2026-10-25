from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.adhoc import (
    _netscape_cookiefile,
    _ydl_cookie_opts,
    analyze_processed,
    platform_from_url,
)


@dataclass
class _Match:
    content_id: str
    score: float
    shared_identifiers: list


def _processed(**claims):
    base = {"promises_returns": False, "has_referral": False,
            "has_license": False, "gambling_content": False}
    base.update(claims)
    return {
        "sha256": "a" * 64, "content_id": "a" * 64, "author": "@scam_channel",
        "text": "вложи 100 получай 1000", "tags": ["casino"],
        "claims": base, "telegram": ["scam"], "wallets": ["USDT-X"], "domains": [],
    }


def test_analysis_shape_and_identifiers():
    out = analyze_processed(_processed(promises_returns=True), matches=[])
    assert out["sha256"] == "a" * 64
    assert out["author"] == "@scam_channel"          # so the UI can offer «watch account»
    assert out["identifiers"]["wallets"] == ["USDT-X"]
    assert out["claims"]["promises_returns"] is True
    assert "score" in out["risk"] and "breakdown" in out["risk"]


def test_platform_detection_for_watch_account():
    assert platform_from_url("https://youtu.be/abc") == "youtube"
    assert platform_from_url("https://www.tiktok.com/@x/video/1") == "tiktok"
    assert platform_from_url("https://www.instagram.com/reel/x") == "instagram"


def test_risk_reflects_text_signals_and_matches():
    p = _processed()
    p["text"] = "Вложи 5000 тг — через неделю получишь 10 000 тг! Пригласи друга — бонус"
    alone = analyze_processed(p, matches=[])["risk"]
    linked = analyze_processed(p, matches=[_Match("c2", 0.9, ["wallet:USDT-X"])] * 5)
    # rules: return ×2 in a week (40) + referral (20) = 60, plus the learned layer (≤ 20);
    # 5 scheme matches add the network factor (+10)
    rules = sum(b["contribution"] for b in alone["breakdown"] if b["factor"] != "ml.similar")
    assert round(rules) == 60 and alone["track"] == "pyramid"
    assert linked["risk"]["score"] == min(100, alone["score"] + 10)
    assert linked["scheme_matches"][0]["content_id"] == "c2"


def test_registry_license_lowers_casino_risk():
    ad = "Казино с выводом на Kaspi, промокод WIN500, ссылка в шапке"
    risky_p, licensed_p = _processed(), _processed(has_license=True)
    risky_p["text"] = licensed_p["text"] = ad
    risky = analyze_processed(risky_p, [])["risk"]["score"]
    licensed = analyze_processed(licensed_p, [])["risk"]["score"]
    assert risky > licensed        # registry-verified license halves the casino score


def test_analyze_endpoints_require_auth():
    client = TestClient(app)
    assert client.post("/api/v1/analyze/url", json={"url": "https://x/y"}).status_code == 401
    assert client.post("/api/v1/analyze/file").status_code == 401


# --- Instagram cookie handling (yt-dlp needs a session in the cookiejar) ------
def test_cookie_header_converts_to_netscape_file(tmp_path):
    path = _netscape_cookiefile(str(tmp_path), "instagram.com", "sessionid=abc123; ds_user_id=42")
    content = open(path, encoding="utf-8").read()
    assert content.startswith("# Netscape HTTP Cookie File")
    lines = [l for l in content.splitlines() if l and not l.startswith("#")]
    assert any("\tsessionid\tabc123" in l for l in lines)
    assert all(l.startswith(".instagram.com\tTRUE\t/\tTRUE\t") for l in lines)   # not session-discarded


def test_cookie_opts_only_for_instagram_when_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "instagram_cookies_file", "")
    monkeypatch.setattr(settings, "instagram_cookie", "sessionid=abc")
    # Instagram URL + cookie configured -> cookiefile injected
    opts = _ydl_cookie_opts("https://www.instagram.com/reel/x", str(tmp_path))
    assert "cookiefile" in opts
    # other platforms never get the Instagram cookie
    assert _ydl_cookie_opts("https://youtu.be/x", str(tmp_path)) == {}


def test_cookies_file_takes_priority_over_header(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "instagram_cookies_file", "/data/ig_cookies.txt")
    monkeypatch.setattr(settings, "instagram_cookie", "sessionid=abc")
    opts = _ydl_cookie_opts("https://www.instagram.com/reel/x", str(tmp_path))
    assert opts == {"cookiefile": "/data/ig_cookies.txt"}


def test_no_instagram_cookie_means_no_opts(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "instagram_cookies_file", "")
    monkeypatch.setattr(settings, "instagram_cookie", "")
    assert _ydl_cookie_opts("https://www.instagram.com/reel/x", str(tmp_path)) == {}
