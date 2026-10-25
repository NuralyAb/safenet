"""Public Telegram channel scrape via the t.me/s/<channel> web preview.

NO Telegram API / login needed: public channels expose their recent posts as HTML
at https://t.me/s/<channel>. We parse the post text + view count so the collector
can feed it through the same pipeline (claims -> risk, identifier extraction) as any
other source. Public channels only — private/closed channels need the Telethon path.

Parsing is best-effort over Telegram's stable widget markup. Pure `parse_posts`
(testable on a fixture) + `fetch_channel` (one httpx GET).
"""
from __future__ import annotations

import html as _html
import re

import httpx

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_MSG_SPLIT = re.compile(r'(?=<div class="tgme_widget_message[ "])')
_POST_ID = re.compile(r'data-post="([^"]+)"')
_TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_VIEWS = re.compile(r'tgme_widget_message_views"[^>]*>([^<]+)<')
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.I)


def normalize_channel(target: str) -> str:
    """'@Name', 't.me/Name', 'https://t.me/s/Name/123' -> 'Name' (bare channel)."""
    t = (target or "").strip()
    t = re.sub(r"^https?://", "", t, flags=re.I)
    t = re.sub(r"^(www\.)?(t\.me|telegram\.me)/", "", t, flags=re.I)
    t = re.sub(r"^s/", "", t, flags=re.I)
    t = t.lstrip("@")
    return t.split("/")[0].split("?")[0]


def _html_to_text(fragment: str) -> str:
    text = _BR.sub("\n", fragment)
    text = _TAG.sub("", text)
    text = _html.unescape(text)
    # collapse runs of blank lines / trailing space
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _parse_count(raw: str) -> int:
    s = (raw or "").strip().replace(",", ".").upper()
    m = re.match(r"^([\d.]+)\s*([KM]?)$", s)
    if not m:
        digits = re.sub(r"\D", "", s)
        return int(digits) if digits else 0
    num = float(m.group(1))
    mult = {"K": 1_000, "M": 1_000_000}.get(m.group(2), 1)
    return int(num * mult)


def parse_posts(html: str, channel: str) -> list[dict]:
    """Extract [{id, url, text, views}] from a t.me/s/<channel> page (oldest->newest)."""
    posts: list[dict] = []
    for block in _MSG_SPLIT.split(html or ""):
        m_id = _POST_ID.search(block)
        if not m_id:
            continue
        post_id = m_id.group(1)                      # "channel/123"
        m_txt = _TEXT.search(block)
        text = _html_to_text(m_txt.group(1)) if m_txt else ""
        m_views = _VIEWS.search(block)
        posts.append({
            "id": post_id,
            "url": f"https://t.me/{post_id}",
            "text": text,
            "views": _parse_count(m_views.group(1)) if m_views else 0,
        })
    return posts


def fetch_channel(target: str, *, limit: int = 20, client: httpx.Client | None = None) -> list[dict]:
    """Fetch the most recent public posts of a channel. Returns [] if none/unavailable."""
    channel = normalize_channel(target)
    if not channel:
        return []
    url = f"https://t.me/s/{channel}"
    c = client or httpx.Client(timeout=20, headers={"User-Agent": _UA}, follow_redirects=True)
    try:
        resp = c.get(url)
        resp.raise_for_status()
        page = resp.text
    finally:
        if client is None:
            c.close()
    posts = parse_posts(page, channel)
    return posts[-limit:] if limit and limit > 0 else posts
