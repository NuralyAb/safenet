import json

import pytest

from app.services.adhoc import DownloadFailed
from app.services.tiktok import extract_from_item, fetch, is_tiktok, parse_item


def _html(item: dict) -> str:
    payload = {"__DEFAULT_SCOPE__": {"webapp.video-detail": {"itemInfo": {"itemStruct": item}}}}
    return ('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
            + json.dumps(payload) + "</script>")


PHOTO_ITEM = {
    "desc": "лучшее онлайн казино без лицензии, заходи",
    "author": {"uniqueId": "casino"},
    "imagePost": {"images": [
        {"imageURL": {"urlList": ["https://cdn/img1.jpg", "https://cdn/img1b.jpg"]}},
        {"imageURL": {"urlList": ["https://cdn/img2.jpg"]}},
    ]},
}
VIDEO_ITEM = {
    "desc": "инвестируй и получи 100%",
    "author": {"uniqueId": "scammer"},
    "video": {"playAddr": "https://cdn/video.mp4"},
}


class _Resp:
    def __init__(self, text="", content=b"", status=200, json_data=None):
        self.text, self.content, self.status_code, self._json = text, content, status, json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._json


class _Client:
    """Fake httpx client: POST → tikwm body, GET page/media. tikwm=None → resolver 'fails'."""
    def __init__(self, page_html: str = "", media: dict | None = None, tikwm: dict | None = None):
        self.page_html, self.media, self.tikwm = page_html, media or {}, tikwm

    def post(self, url, data=None, headers=None):
        return _Resp(json_data=self.tikwm or {"code": -1, "msg": "fail"})

    def get(self, url, headers=None):
        if url in self.media:
            return _Resp(content=self.media[url])
        return _Resp(text=self.page_html)


def test_is_tiktok():
    assert is_tiktok("https://www.tiktok.com/@x/photo/1")
    assert is_tiktok("https://vt.tiktok.com/ZSCRfBun9/")
    assert not is_tiktok("https://youtu.be/x")


def test_parse_and_extract_photo_post():
    info = extract_from_item(parse_item(_html(PHOTO_ITEM)))
    assert info["kind"] == "photo"
    assert info["author"] == "casino"
    assert "казино" in info["caption"]
    assert info["image_urls"] == ["https://cdn/img1.jpg", "https://cdn/img2.jpg"]  # first url per image


def test_parse_and_extract_video_post():
    info = extract_from_item(parse_item(_html(VIDEO_ITEM)))
    assert info["kind"] == "video"
    assert info["video_url"] == "https://cdn/video.mp4"
    assert info["author"] == "scammer"


def test_parse_anonymous_or_garbage_returns_none():
    # anti-bot response: rehydration JSON present but the post scope is stripped
    stripped = ('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
                + json.dumps({"__DEFAULT_SCOPE__": {"webapp.app-context": {}}}) + "</script>")
    assert parse_item(stripped) is None
    assert parse_item("<html>no json here</html>") is None


def test_fetch_without_cookie_fails_when_resolver_down():
    # tikwm 'fails' (code -1) and no cookie -> actionable hint, no real network
    with pytest.raises(DownloadFailed) as exc:
        fetch("https://www.tiktok.com/@x/photo/1", cookie="", client=_Client(tikwm={"code": -1}))
    assert "TIKTOK_COOKIE" in str(exc.value)


# --- tikwm resolver (primary path, no cookie needed) -------------------------
TIKWM_PHOTO = {"code": 0, "data": {
    "title": "лучшее онлайн казино без лицензии", "author": {"unique_id": "casino"},
    "images": ["https://cdn/i1.jpg", "https://cdn/i2.jpg"],
    "play_count": 817, "digg_count": 8, "comment_count": 2, "share_count": 2}}
TIKWM_VIDEO = {"code": 0, "data": {
    "title": "инвестируй 100%", "author": {"unique_id": "scammer"}, "images": [],
    "hdplay": "https://cdn/v.mp4", "play_count": 1000, "digg_count": 50,
    "comment_count": 5, "share_count": 3}}


def test_extract_from_tikwm_photo_and_video():
    from app.services.tiktok import extract_from_tikwm
    p = extract_from_tikwm(TIKWM_PHOTO["data"])
    assert p["kind"] == "photo" and p["author"] == "casino"
    assert p["reach"] == {"views": 817, "likes": 8, "comments": 2, "shares": 2}
    v = extract_from_tikwm(TIKWM_VIDEO["data"])
    assert v["kind"] == "video" and v["video_url"] == "https://cdn/v.mp4"


def test_fetch_via_tikwm_photo_no_cookie():
    client = _Client(media={"https://cdn/i1.jpg": b"I1", "https://cdn/i2.jpg": b"I2"},
                     tikwm=TIKWM_PHOTO)
    out = fetch("https://vt.tiktok.com/x/", cookie="", client=client)   # no cookie needed
    assert out["kind"] == "photo" and out["images"] == [b"I1", b"I2"]
    assert out["author"] == "casino" and out["reach"]["views"] == 817


def test_fetch_via_tikwm_video_no_cookie():
    client = _Client(media={"https://cdn/v.mp4": b"VID"}, tikwm=TIKWM_VIDEO)
    out = fetch("https://vt.tiktok.com/x/", cookie="", client=client)
    assert out["kind"] == "video" and out["media"] == b"VID"
    assert out["reach"]["likes"] == 50


def test_tikwm_relative_media_url_made_absolute():
    from app.services.tiktok import extract_from_tikwm
    v = extract_from_tikwm({"hdplay": "/video/tos/abc.mp4"})
    assert v["video_url"] == "https://www.tikwm.com/video/tos/abc.mp4"


def test_fetch_photo_downloads_all_images():
    client = _Client(_html(PHOTO_ITEM),
                     {"https://cdn/img1.jpg": b"IMG1", "https://cdn/img2.jpg": b"IMG2"})
    out = fetch("https://www.tiktok.com/@casino/photo/1", cookie="sess=1", client=client)
    assert out["kind"] == "photo"
    assert out["images"] == [b"IMG1", b"IMG2"]
    assert out["author"] == "casino" and "казино" in out["caption"]


def test_fetch_video_downloads_media():
    client = _Client(_html(VIDEO_ITEM), {"https://cdn/video.mp4": b"VIDEO"})
    out = fetch("https://www.tiktok.com/@scammer/video/1", cookie="sess=1", client=client)
    assert out["kind"] == "video" and out["media"] == b"VIDEO"
    assert out["author"] == "scammer"


def test_fetch_with_cookie_but_stripped_page_fails():
    stripped = ('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
                + json.dumps({"__DEFAULT_SCOPE__": {}}) + "</script>")
    with pytest.raises(DownloadFailed):
        fetch("https://www.tiktok.com/@x/photo/1", cookie="sess=1",
              client=_Client(stripped, {}))
