"""Shared yt-dlp base for video platforms (YouTube/TikTok/Instagram public).

yt-dlp handles all three; subclasses only supply the channel URL. Heavy import is
lazy so the registry loads without yt-dlp present. Real network execution requires
yt-dlp installed (in requirements) and outbound access (collector-worker only).
"""
from __future__ import annotations

from app.services.extract import extract_identifiers
from app.workers.collectors.base import BaseCollector, CollectedItem


class YtDlpCollector(BaseCollector):
    tos_warning: str = ""

    def channel_url(self, target: str) -> str:
        raise NotImplementedError

    def health(self) -> bool:
        try:
            import yt_dlp  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, target: str, *, limit: int = 20) -> list[CollectedItem]:
        return self._extract(self.channel_url(target), limit)

    def _cookiefile(self, tmp: str) -> str | None:
        """Resolve a Netscape cookies file for this source (login-gated platforms).

        Priority: an explicit cookies.txt path, else a raw `Cookie:` header converted
        on the fly. YouTube needs none. Returns a path or None.
        """
        import os

        from app.core.config import settings

        spec = {
            "instagram": (settings.instagram_cookies_file, settings.instagram_cookie, ".instagram.com"),
            "tiktok": ("", settings.tiktok_cookie, ".tiktok.com"),
        }.get(self.source)
        if not spec:
            return None
        file_path, raw_header, domain = spec
        if file_path:
            return file_path
        if raw_header:
            from app.services.cookies import header_to_netscape
            path = os.path.join(tmp, "cookies.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(header_to_netscape(raw_header, domain))
            return path
        return None

    def _extract(self, target_url: str, limit: int) -> list[CollectedItem]:
        import os
        import tempfile

        import yt_dlp

        items: list[CollectedItem] = []
        with tempfile.TemporaryDirectory() as tmp:
            opts = {
                "quiet": True, "noprogress": True, "playlistend": limit,
                "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
                "format": "bestvideo*+bestaudio/best",
                "merge_output_format": "mp4",
                # subtitles intentionally omitted here — they rate-limit (429) and abort
                # the whole sweep; the pipeline's Whisper transcribes speech anyway.
                "ignoreerrors": True,
            }
            cookiefile = self._cookiefile(tmp)
            if cookiefile:
                opts["cookiefile"] = cookiefile
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                if info is None:
                    # Extraction yielded nothing (login-gated platform without a valid
                    # cookie, private/empty profile, or a transient block). Fail with a
                    # clear, actionable message instead of an opaque NoneType crash.
                    raise RuntimeError(
                        f"{self.source}: не удалось получить данные для {target_url}. "
                        "Вероятно, нужен действительный логин-cookie "
                        f"({self.source.upper()}_COOKIE / _COOKIES_FILE) или профиль "
                        "приватный/пустой."
                    )
                for e in info.get("entries") or [info]:
                    if not e:
                        continue
                    try:
                        with open(ydl.prepare_filename(e), "rb") as fh:
                            media = fh.read()
                    except OSError:
                        continue
                    # Fold subtitles into the analysed text (the real pitch is often spoken).
                    text = e.get("description") or ""
                    subs = self._read_subtitles(tmp, str(e.get("id", "")))
                    if subs:
                        text = f"{text}\n{subs}".strip() if text else subs
                    ids = extract_identifiers(text)
                    items.append(CollectedItem(
                        source=self.source, external_id=str(e.get("id", "")),
                        author=e.get("uploader") or "",
                        url=e.get("webpage_url") or "", media=media,
                        content_type="video/mp4", ext="mp4", text=text,
                        telegram=ids["telegram"], wallets=ids["wallets"], domains=ids["domains"],
                        reach={"views": e.get("view_count"), "likes": e.get("like_count"),
                               "comments": e.get("comment_count"), "shares": e.get("repost_count")},
                    ))
        return items

    @staticmethod
    def _read_subtitles(tmp: str, video_id: str) -> str:
        import glob
        import os

        from app.services.subtitles import clean_subtitles

        for lang in ("ru", "en"):
            matches = glob.glob(os.path.join(tmp, f"{video_id}.{lang}.vtt"))
            if matches:
                try:
                    with open(matches[0], encoding="utf-8", errors="replace") as fh:
                        return clean_subtitles(fh.read())
                except OSError:
                    continue
        return ""
