"""TikTok ingestion — videos AND photo/slideshow posts.

Empirically (verified from a datacenter IP): TikTok serves NO post data to an
anonymous request — the page loads but its rehydration JSON is stripped, oEmbed
returns 400, and yt-dlp reports `/photo/` as "Unsupported URL". So a logged-in
session cookie is REQUIRED. Provide it via the TIKTOK_COOKIE setting (a raw
`Cookie:` header copied from a logged-in browser). Without it we fail with a clear,
actionable message instead of a misleading one.

CAVEAT: collecting real TikTok content is against TikTok's ToS and the prototype
rule (external APIs = synthetic/demo data only — see CLAUDE.md / ADR-0005). This
path exists for authorized testing; keep real-case data off external services.

The JSON parsers (`parse_item`, `extract_from_item`) are pure and unit-tested; the
network fetch is best-effort and isolated here.
"""
from __future__ import annotations

import json
import re

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_RE_REHYDRATION = re.compile(
    r'__UNIVERSAL_DATA_FOR_REHYDRATION__[^>]*>(.*?)</script>', re.S
)
_COOKIE_HINT = ("TikTok не отдаёт данные поста без авторизации (анти-бот). Добавьте "
                "TIKTOK_COOKIE в .env (заголовок Cookie из залогиненного браузера) "
                "или загрузите файл во вкладке «Загрузить файл».")


def is_tiktok(url: str) -> bool:
    return "tiktok.com" in (url or "").lower()


def parse_item(html: str) -> dict | None:
    """Pure: pull the post's `itemStruct` out of the page's rehydration JSON.

    Returns None when the data is absent (anonymous/anti-bot response) — the caller
    turns that into the cookie hint.
    """
    m = _RE_REHYDRATION.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    scope = data.get("__DEFAULT_SCOPE__", {}) if isinstance(data, dict) else {}
    detail = scope.get("webapp.video-detail", {}) or {}
    item = (detail.get("itemInfo", {}) or {}).get("itemStruct")
    return item or None


def _reach(item: dict) -> dict:
    """Map TikTok stats -> canonical reach («охват»)."""
    stats = item.get("stats") or item.get("statsV2") or {}
    return {"views": stats.get("playCount"), "likes": stats.get("diggCount"),
            "comments": stats.get("commentCount"), "shares": stats.get("shareCount")}


def extract_from_item(item: dict) -> dict:
    """Pure: normalize an `itemStruct` -> {kind, caption, author, reach, image_urls, video_url}."""
    caption = item.get("desc") or ""
    author = (item.get("author") or {}).get("uniqueId") or ""
    reach = _reach(item)
    image_post = item.get("imagePost") or {}
    if image_post:
        urls = []
        for img in image_post.get("images", []):
            url_list = (img.get("imageURL", {}) or {}).get("urlList") or []
            if url_list:
                urls.append(url_list[0])
        return {"kind": "photo", "caption": caption, "author": author, "reach": reach,
                "image_urls": urls, "video_url": ""}
    video = item.get("video") or {}
    return {"kind": "video", "caption": caption, "author": author, "reach": reach,
            "image_urls": [], "video_url": video.get("playAddr") or video.get("downloadAddr") or ""}


_TIKWM_API = "https://www.tikwm.com/api/"


def _abs(u: str) -> str:
    """tikwm sometimes returns host-relative media paths -> make them absolute."""
    if not u:
        return u
    return u if u.startswith("http") else f"https://www.tikwm.com{u}"


def extract_from_tikwm(d: dict) -> dict:
    """Pure: normalize a tikwm `data` object -> {kind, caption, author, reach, image_urls, video_url}."""
    caption = d.get("title") or d.get("content_desc") or ""
    author = (d.get("author") or {}).get("unique_id") or ""
    reach = {"views": d.get("play_count"), "likes": d.get("digg_count"),
             "comments": d.get("comment_count"), "shares": d.get("share_count")}
    images = [_abs(u) for u in (d.get("images") or []) if u]
    if images:
        return {"kind": "photo", "caption": caption, "author": author, "reach": reach,
                "image_urls": images, "video_url": ""}
    return {"kind": "video", "caption": caption, "author": author, "reach": reach,
            "image_urls": [], "video_url": _abs(d.get("hdplay") or d.get("play") or d.get("wmplay") or "")}


def _download(info: dict, *, client) -> dict:
    """Download the media for a normalized {kind, image_urls|video_url, …} info dict."""
    from app.services.adhoc import DownloadFailed

    ref = {"Referer": "https://www.tiktok.com/"}
    if info["kind"] == "photo":
        images: list[bytes] = []
        for u in info["image_urls"]:
            try:
                ir = client.get(u, headers=ref)
                if ir.status_code == 200 and ir.content:
                    images.append(ir.content)
            except Exception:  # noqa: BLE001 — skip an unreachable image, keep the rest
                continue
        if not images:
            raise DownloadFailed("Картинки TikTok-поста недоступны. Загрузите файл вручную.")
        return {"kind": "photo", "caption": info["caption"], "author": info["author"],
                "reach": info.get("reach", {}), "images": images}

    if not info["video_url"]:
        raise DownloadFailed("Видео-URL TikTok не найден. Загрузите файл вручную.")
    vr = client.get(info["video_url"], headers=ref)
    vr.raise_for_status()
    if not vr.content:
        raise DownloadFailed("Видео TikTok пустое/недоступно. Загрузите файл вручную.")
    return {"kind": "video", "caption": info["caption"], "author": info["author"],
            "reach": info.get("reach", {}), "media": vr.content}


def _via_tikwm(url: str, *, client) -> dict | None:
    """Resolve a TikTok post via the public tikwm API (handles signing/proxy, no cookie).

    This is how downloader services work without a TikTok Research API — tikwm fronts
    the unofficial API from residential infra, so it works from a datacenter IP where
    a direct cookie request just gets a captcha. Returns None if tikwm can't resolve it.
    """
    try:
        r = client.post(_TIKWM_API, data={"url": url, "hd": "1"})
        r.raise_for_status()
        body = r.json()
    except Exception:  # noqa: BLE001 — tikwm down / rate-limited -> let the caller fall back
        return None
    if not isinstance(body, dict) or body.get("code") != 0:
        return None
    info = extract_from_tikwm(body.get("data") or {})
    try:
        return _download(info, client=client)
    except Exception:  # noqa: BLE001
        return None


def fetch(url: str, cookie: str = "", *, client=None) -> dict:
    """Fetch a TikTok post (video OR photo) -> {kind, caption, author, reach, media?|images?}.

    Primary path: the public tikwm resolver (no cookie, works from a datacenter IP).
    Fallback: direct page parse with a session cookie (often blocked by captcha on
    datacenter IPs — see the empirical note at the top of this module).
    """
    import httpx

    from app.services.adhoc import DownloadFailed

    own = client is None
    c = client or httpx.Client(headers={"User-Agent": _UA, "Accept-Language": "ru,en;q=0.9"},
                               follow_redirects=True, timeout=30)
    try:
        via = _via_tikwm(url, client=c)
        if via:
            return via

        # Fallback: cookie-based page parse.
        if not cookie:
            raise DownloadFailed(
                "TikTok-резолвер недоступен, а TIKTOK_COOKIE не задан. Добавьте cookie "
                "залогиненного аккаунта в .env или загрузите файл во вкладке «Загрузить файл»."
            )
        resp = c.get(url, headers={"Cookie": cookie})
        resp.raise_for_status()
        item = parse_item(resp.text)
        if not item:
            raise DownloadFailed(
                "Не удалось получить данные TikTok-поста (резолвер не ответил, а прямой "
                "запрос упёрся в капчу/устаревшие cookies). Обновите TIKTOK_COOKIE или "
                "загрузите файл."
            )
        return _download(extract_from_item(item), client=c)
    finally:
        if own:
            c.close()
