"""Concrete source adapters.

YouTube  — cleanest; public videos via yt-dlp (official Data API also possible).
TikTok   — public videos via yt-dlp; ⚠ scraping violates ToS, fragile.
Instagram— public posts via yt-dlp; ⚠ ToS; Graph API only for business accounts you own.
Telegram — MTProto via Telethon (separate; needs api_id/hash + session).
WhatsApp — NOT SUPPORTED: E2E-encrypted, no public content to collect.
"""
from __future__ import annotations

from app.workers.collectors._ytdlp import YtDlpCollector
from app.workers.collectors.base import BaseCollector, CollectedItem
from app.workers.collectors.registry import register


def youtube_search_expr(query: str, limit: int) -> str:
    """yt-dlp pseudo-URL that searches YouTube (proactive discovery of new objects)."""
    return f"ytsearch{limit}:{query}"


@register("youtube")
class YouTubeCollector(YtDlpCollector):
    # Many accounts post ONLY Shorts (no classic /videos tab), so sweep both tabs.
    TABS = ("videos", "shorts")

    def channel_url(self, target: str) -> str:
        return f"https://www.youtube.com/@{target.lstrip('@')}/videos"

    def fetch(self, target: str, *, limit: int = 20) -> list[CollectedItem]:
        handle = target.lstrip("@")
        items: list[CollectedItem] = []
        for tab in self.TABS:
            if len(items) >= limit:
                break
            try:
                items += self._extract(f"https://www.youtube.com/@{handle}/{tab}", limit - len(items))
            except Exception:  # noqa: BLE001 — a missing tab (no /videos or no /shorts) is normal
                continue
        if not items:
            raise RuntimeError(
                f"youtube: у канала @{handle} нет видео во вкладках videos/shorts "
                "(или профиль пуст/закрыт)."
            )
        return items

    def search(self, query: str, *, limit: int = 20) -> list[CollectedItem]:
        return self._extract(youtube_search_expr(query, limit), limit)


@register("tiktok")
class TikTokCollector(YtDlpCollector):
    tos_warning = "Unofficial: scraping TikTok violates ToS; fragile, may need proxy rotation."

    def channel_url(self, target: str) -> str:
        return f"https://www.tiktok.com/@{target.lstrip('@')}"


@register("instagram")
class InstagramCollector(YtDlpCollector):
    tos_warning = "Unofficial: public posts only; violates ToS. Graph API only for owned business accounts."

    def channel_url(self, target: str) -> str:
        return f"https://www.instagram.com/{target.lstrip('@')}/"


@register("telegram")
class TelegramCollector(BaseCollector):
    """Public channel scrape via the t.me/s/<channel> web preview — no API/login.

    Each post's text becomes a CollectedItem (the text itself is the WORM evidence);
    the runner hashes/stores it and the normal pipeline extracts claims/risk and
    hard identifiers. Private/closed channels need the Telethon (MTProto) path.
    """
    source = "telegram"

    def health(self) -> bool:
        return True   # only needs public HTTP to t.me

    def fetch(self, target: str, *, limit: int = 20) -> list[CollectedItem]:
        from app.services import telegram_web
        from app.services.extract import extract_identifiers

        channel = telegram_web.normalize_channel(target)
        items: list[CollectedItem] = []
        for post in telegram_web.fetch_channel(target, limit=limit):
            text = post.get("text", "")
            if not text:
                continue   # media-only post: nothing for the text pipeline to analyse
            ids = extract_identifiers(text)
            items.append(CollectedItem(
                source="telegram",
                external_id=post["id"],
                author=f"@{channel}",
                url=post["url"],
                media=text.encode("utf-8"),          # the post text is the evidence
                content_type="text/plain; charset=utf-8",
                ext="txt",
                text=text,
                telegram=ids["telegram"],
                wallets=ids["wallets"],
                domains=ids["domains"],
                reach={"views": post.get("views", 0)},
            ))
        return items


@register("whatsapp")
class WhatsAppCollector(BaseCollector):
    """NOT SUPPORTED — kept registered to fail loudly with the reason."""

    def health(self) -> bool:
        return False

    def fetch(self, target: str, *, limit: int = 20) -> list[CollectedItem]:
        raise NotImplementedError(
            "WhatsApp cannot be monitored: it is end-to-end encrypted with no public "
            "content feed. There is no lawful/technical way to collect third-party "
            "WhatsApp videos. The Business API only handles your own org's messages."
        )
