"""Ad-hoc single-video analysis — «проверь вот это видео» (URL or uploaded file).

Runs one item through the full pipeline synchronously and returns the analysis.
`analyze_processed` (the result assembly + single-item risk) is pure and tested;
`run_analysis` wires the heavy I/O (evidence, ffmpeg, AI, fingerprint search).
"""
from __future__ import annotations


class DownloadFailed(Exception):
    """The URL could not be downloaded (unsupported / auth-required / not found)."""


def _download_error_message(url: str, exc: Exception) -> str:
    """Build an honest, host-aware message from the real yt-dlp error.

    The previous text always blamed Instagram/TikTok, which is misleading when a
    YouTube link simply fails (e.g. «Video unavailable»). Surface the actual reason
    and point at the reliable fallback (upload the file).
    """
    import re

    raw = (str(exc) or "").strip()
    last = raw.splitlines()[-1] if raw else ""
    # strip yt-dlp's "ERROR: [extractor] <id>: " noise -> the human reason
    clean = re.sub(r"^ERROR:\s*", "", last)
    clean = re.sub(r"^\[[^\]]+\]\s*", "", clean)
    clean = re.sub(r"^[\w.-]+:\s*", "", clean).strip()

    low = (url or "").lower()
    reason = (clean or last).lower()
    # TikTok/Instagram «photo»/slideshow posts are image carousels, NOT video —
    # yt-dlp reports them as "Unsupported URL". The video pipeline can't process them.
    if "/photo/" in low or "/photo/" in reason or ("unsupported url" in reason and "photo" in reason):
        return ("Это фото-пост (слайд-шоу из картинок), а не видео — такой контент "
                "видео-анализатор не обрабатывает. Откройте именно ВИДЕО-ролик "
                "(.../video/...) или загрузите файл во вкладке «Загрузить файл».")

    # Private / followers-only / login-walled content (any platform).
    if any(k in reason for k in ("registered users", "follow this account", "login required",
                                 "log in", "private", "only available for")):
        return ("Это закрытый/приватный пост (доступен только подписчикам или после входа) — "
                "анонимно его скачать нельзя. Возьмите публичную ссылку или загрузите файл "
                "во вкладке «Загрузить файл».")

    if "instagram" in low:
        from app.core.config import settings
        if settings.instagram_cookie or settings.instagram_cookies_file:
            hint = ("Instagram отклонил запрос даже с cookies — они устарели/невалидны "
                    "или сработал rate-limit. Обновите INSTAGRAM_COOKIE из залогиненного "
                    "браузера или загрузите файл во вкладке «Загрузить файл».")
        else:
            hint = ("Instagram не отдаёт видео без авторизации. Задайте INSTAGRAM_COOKIE "
                    "(заголовок Cookie из залогиненного браузера) в .env, либо загрузите "
                    "файл во вкладке «Загрузить файл».")
    elif "tiktok" in low:
        hint = ("TikTok часто не отдаёт видео без авторизации/cookies. "
                "Скачайте ролик и загрузите файл во вкладке «Загрузить файл».")
    else:
        hint = ("Видео может быть удалено, приватным или иметь возрастное/региональное "
                "ограничение — такие ролики не скачиваются без входа. Попробуйте другую "
                "ссылку или загрузите файл во вкладке «Загрузить файл».")
    detail = f" ({clean})" if clean and len(clean) < 160 else ""
    return f"Не удалось скачать видео по ссылке{detail}. {hint}"


GRAPH_ID_KEYS = ("telegram", "wallets", "domains", "phones", "cards", "promo_codes", "short_links")


def graph_identifiers(processed: dict) -> dict:
    """The identifier lists GraphBuilder.link_identifiers accepts, from a processed item."""
    return {k: processed.get(k, []) or [] for k in GRAPH_ID_KEYS}


def platform_from_url(url: str) -> str:
    """Map a URL to a collector source (so 'watch this account' uses the right adapter)."""
    u = (url or "").lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    return "url"


def analyze_processed(processed: dict, matches: list) -> dict:
    """Assemble the analysis result + single-item risk from processed features. Pure."""
    from app.services.content_scoring import normalize_reach, priority_from, score_content
    from app.services.safenet import assessment_dict

    claims = processed.get("claims", {})
    cid = processed.get("content_id", "")
    # SafeNet per-track score from the pipeline's signals; scheme matches drive «повторяемость».
    a = score_content(claims, safenet=processed.get("safenet"),
                      text=None if processed.get("safenet") else processed.get("text", ""),
                      scheme_matches=len(matches), evidence_ids=[cid] if cid else [],
                      has_license=claims.get("has_license", False))
    reach = normalize_reach(processed.get("reach"))
    risk = assessment_dict(a)
    return {
        "sha256": processed.get("sha256"),
        "track": risk["track"],
        "language": risk["language"],
        "caption": processed.get("caption", ""),
        "text": processed.get("text", ""),
        "transcript": processed.get("transcript", ""),    # speech — retained as evidence
        "ocr_text": processed.get("ocr_text", ""),        # on-screen text — retained as evidence
        "tags": processed.get("tags", []),
        "author": processed.get("author", ""),
        "reach": reach,                                   # audience «охват»
        "priority": priority_from(a.score, reach["views"]),  # risk × reach (triage rank)
        "claims": claims,
        # Chain-of-custody fields (persisted into the Evidence row by the API layer).
        "evidence_key": processed.get("evidence_key", processed.get("raw_key", "")),
        "size": processed.get("size", 0),
        "content_type": processed.get("content_type", ""),
        "identifiers": {
            "telegram": processed.get("telegram", []),
            "wallets": processed.get("wallets", []),
            "domains": processed.get("domains", []),
            "phones": processed.get("phones", []),
            "cards": processed.get("cards", []),
            "promo_codes": processed.get("promo_codes", []),
            "short_links": processed.get("short_links", []),
        },
        "risk": risk,
        "scheme_matches": [
            {"content_id": m.content_id, "score": m.score, "shared": m.shared_identifiers}
            for m in matches
        ],
    }


def run_analysis(media: bytes | None = None, *, source: str, url: str = "", caption: str = "",
                 author: str = "", images: list[bytes] | None = None,
                 reach: dict | None = None) -> dict:
    """Full pipeline on one item: evidence -> ffmpeg -> AI -> fingerprint -> risk.

    `media` = one video (ffmpeg extracts audio + frames). `images` = a photo/slideshow
    post (TikTok carousel) — fed straight to the multi-frame vision/OCR path, no ffmpeg.
    """
    from app.core.config import settings
    from app.db.clients import minio_client, qdrant_client
    from app.services.ai.factory import (
        get_embedder, get_face_embedder, get_llm, get_ocr,
        get_speaker_embedder, get_transcriber, get_vision_tagger,
    )
    from app.db.licensed_repo import load_active_identifiers
    from app.services.evidence import EvidenceStore
    from app.services.extract import extract_identifiers
    from app.services.fingerprint import FingerprintStore
    from app.services.media import enrich_with_media
    from app.services.pipeline import extract_features, fingerprint_from_processed

    images = images or []
    is_photo = media is None and bool(images)
    primary = media if media is not None else (images[0] if images else b"")

    store = EvidenceStore(minio_client(), settings.minio_raw_bucket, settings.minio_evidence_bucket)
    ref = store.store(primary, source,
                      content_type="image/jpeg" if is_photo else "video/mp4",
                      ext="jpg" if is_photo else "mp4")
    ids = extract_identifiers(caption)
    collected = {
        "content_id": ref.sha256, "source": source, "sha256": ref.sha256, "raw_key": ref.raw_key,
        "evidence_key": ref.evidence_key, "size": ref.size, "content_type": ref.content_type,
        "author": author, "url": url, "text": caption, "reach": reach or {},
        "telegram": ids["telegram"], "wallets": ids["wallets"], "domains": ids["domains"],
    }
    if images:
        collected["images"] = images        # photo carousel -> multi-frame vision/OCR
        collected["image"] = images[0]
    else:
        collected["media"] = media
    collected = enrich_with_media(collected)          # video: ffmpeg audio+frame; photo: no-op
    processed = extract_features(
        get_embedder(), collected,
        transcriber=get_transcriber(), vision=get_vision_tagger(), llm=get_llm(),
        ocr=get_ocr(), face_embedder=get_face_embedder(), speaker_embedder=get_speaker_embedder(),
        licensed_registry=load_active_identifiers(),
    )

    matches = []
    try:
        fps = FingerprintStore(qdrant_client())
        fps.init_collection()
        fp = fingerprint_from_processed(processed)
        fps.upsert(fp)
        matches = fps.search_similar(fp)
    except Exception:  # noqa: BLE001 — fingerprint search is best-effort
        pass

    # Populate the Fraud Graph from the extracted identifiers (real data).
    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import GraphBuilder

        if author:
            GraphBuilder(neo4j_driver()).link_identifiers(
                author, **graph_identifiers(processed), source="analyze")
    except Exception:  # noqa: BLE001 — graph write is best-effort
        pass

    result = analyze_processed(processed, matches)
    result["source"] = source            # so the UI can «watch this account» on the right adapter
    return result


def run_text_analysis(text: str, *, kind: str = "post", author: str = "", source: str = "text",
                      url: str = "") -> dict:
    """Analyse a TEXT item (post caption, stream transcript, chat message, OCR'd banner).

    Same chain as a video minus ffmpeg: evidence (the text itself is hashed + stored
    to WORM) -> SafeNet signals (+ optional LLM) -> fingerprint -> graph -> score.
    """
    from app.core.config import settings
    from app.db.clients import minio_client, qdrant_client
    from app.services.ai.factory import get_embedder, get_llm
    from app.services.evidence import EvidenceStore
    from app.services.extract import extract_identifiers
    from app.services.fingerprint import FingerprintStore
    from app.services.pipeline import extract_features, fingerprint_from_processed

    raw = (text or "").encode("utf-8")
    try:
        store = EvidenceStore(minio_client(), settings.minio_raw_bucket, settings.minio_evidence_bucket)
        ref = store.store(raw, source, content_type="text/plain; charset=utf-8", ext="txt")
        sha, raw_key, ev_key, size = ref.sha256, ref.raw_key, ref.evidence_key, ref.size
    except Exception:  # noqa: BLE001 — object storage down: still hash for chain of custody
        import hashlib
        sha, raw_key, ev_key, size = hashlib.sha256(raw).hexdigest(), "", "", len(raw)

    ids = extract_identifiers(text)
    segment_key = {"stream": "transcript", "ocr": "ocr"}.get(kind)
    collected = {
        "content_id": sha, "source": source, "sha256": sha, "raw_key": raw_key, "evidence_key": ev_key,
        "size": size, "content_type": "text/plain", "author": author, "url": url,
        "text": "" if segment_key else text, "reach": {},
        "telegram": ids["telegram"], "wallets": ids["wallets"], "domains": ids["domains"],
    }
    try:
        llm = get_llm()
    except Exception:  # noqa: BLE001
        llm = None
    processed = extract_features(get_embedder(), collected, llm=llm)
    if segment_key:              # stream transcript / OCR text keep their evidence role
        from app.services.safenet import detect
        det = detect([(segment_key, text)], llm=llm)
        processed["safenet"] = det.to_dict()
        processed[segment_key if segment_key == "transcript" else "ocr_text"] = text
        processed["text"] = text
        for k in ("phones", "cards", "promo_codes", "short_links"):
            processed[k] = det.identifiers.get(k, [])

    matches = []
    try:
        fps = FingerprintStore(qdrant_client())
        fps.init_collection()
        fp = fingerprint_from_processed(processed)
        fps.upsert(fp)
        matches = fps.search_similar(fp)
    except Exception:  # noqa: BLE001 — fingerprint search is best-effort
        pass
    if author:
        try:
            from app.db.clients import neo4j_driver
            from app.services.graph_builder import GraphBuilder
            GraphBuilder(neo4j_driver()).link_identifiers(author, **graph_identifiers(processed), source="analyze")
        except Exception:  # noqa: BLE001
            pass
    result = analyze_processed(processed, matches)
    result["source"] = source
    result["kind"] = kind
    return result


def _author_from_info(info: dict) -> str:
    """Prefer a readable @handle. yt-dlp gives Instagram a NUMERIC uploader_id, but the
    real handle lands in `channel` (e.g. 'craftbet') or the uploader_url tail."""
    uid = str(info.get("uploader_id") or "")
    if uid and not uid.isdigit():
        return uid
    chan = str(info.get("channel") or "")
    if chan and not chan.isdigit():
        return chan
    for key in ("uploader_url", "channel_url"):
        u = info.get(key) or ""
        handle = u.rstrip("/").split("/")[-1] if u else ""
        if handle and not handle.isdigit():
            return handle
    return uid or info.get("uploader") or ""


def _netscape_cookiefile(tmp_dir: str, domain: str, cookie_header: str) -> str:
    """Convert a raw `name=value; name2=value2` Cookie header into a Netscape
    cookies.txt that yt-dlp's cookiejar can load (its extractors read auth cookies
    like Instagram's `sessionid` from the jar, not from an HTTP header)."""
    import os
    path = os.path.join(tmp_dir, "cookies.txt")
    lines = ["# Netscape HTTP Cookie File\n"]
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if name:
            # domain  include_subdomains  path  secure  expiry  name  value
            lines.append(f".{domain}\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    return path


def _ydl_cookie_opts(url: str, tmp_dir: str) -> dict:
    """yt-dlp cookie options for sites that require a logged-in session (Instagram).

    A cookies.txt path (INSTAGRAM_COOKIES_FILE) wins; otherwise a raw Cookie header
    (INSTAGRAM_COOKIE) is converted to one. Empty config -> no cookies (will fail
    with the actionable Instagram message)."""
    from app.core.config import settings
    if "instagram.com" in (url or "").lower():
        if settings.instagram_cookies_file:
            return {"cookiefile": settings.instagram_cookies_file}
        if settings.instagram_cookie:
            return {"cookiefile": _netscape_cookiefile(tmp_dir, "instagram.com", settings.instagram_cookie)}
    return {}


def fetch_url(url: str) -> tuple[bytes, str, str, dict]:
    """Download a single video by URL (yt-dlp) -> (media, caption+subtitles, author, reach)."""
    import os
    import tempfile

    import yt_dlp
    from yt_dlp.utils import DownloadError

    from app.workers.collectors._ytdlp import YtDlpCollector

    import glob

    base = {"quiet": True, "noprogress": True}
    with tempfile.TemporaryDirectory() as tmp:
        outtmpl = os.path.join(tmp, "%(id)s.%(ext)s")
        cookie_opts = _ydl_cookie_opts(url, tmp)   # logged-in session for Instagram, if configured
        # Pass 1 — the video itself (reliable; subtitles NOT requested so they can't abort it).
        try:
            with yt_dlp.YoutubeDL({**base, **cookie_opts, "outtmpl": outtmpl,
                                   "format": "bestvideo*+bestaudio/best",
                                   "merge_output_format": "mp4"}) as ydl:
                info = ydl.extract_info(url, download=True)
                if info.get("entries"):
                    info = (info["entries"] or [None])[0]
                if not info:
                    raise DownloadError("no video found at URL")
                vid = str(info.get("id", ""))
                path = ydl.prepare_filename(info)
                if not os.path.exists(path):           # merged output may differ in ext
                    cands = [p for ext in ("mp4", "mkv", "webm", "mov")
                             for p in glob.glob(os.path.join(tmp, f"{vid}.{ext}"))]
                    if not cands:
                        raise DownloadError("downloaded file not found (no playable format)")
                    path = cands[0]
                with open(path, "rb") as fh:
                    media = fh.read()
                caption = info.get("description") or ""
                author = _author_from_info(info)
                reach = {"views": info.get("view_count"), "likes": info.get("like_count"),
                         "comments": info.get("comment_count"), "shares": info.get("repost_count")}
        except (DownloadError, OSError) as exc:
            raise DownloadFailed(_download_error_message(url, exc)) from exc

        # Pass 2 — subtitles (best-effort; a 429/failure is ignored — Whisper covers speech).
        try:
            with yt_dlp.YoutubeDL({**base, **cookie_opts, "outtmpl": outtmpl, "skip_download": True,
                                   "writesubtitles": True, "writeautomaticsub": True,
                                   "subtitleslangs": ["ru", "en"], "subtitlesformat": "vtt"}) as ydl2:
                ydl2.download([url])
            subs = YtDlpCollector._read_subtitles(tmp, vid)
            if subs:
                caption = f"{caption}\n{subs}".strip() if caption else subs
        except Exception:  # noqa: BLE001 — subtitles are optional
            pass
    return media, caption, author, reach


def fetch_media(url: str) -> dict:
    """Route a URL to the right fetcher -> normalized payload for run_analysis.

    TikTok (videos AND photo/slideshow posts) goes through the cookie-based TikTok
    fetcher; everything else (YouTube/Instagram/direct) uses yt-dlp. Returns
    {media|None, images[], caption, author, source, reach}; raises DownloadFailed on failure.
    """
    from app.core.config import settings
    from app.services import runtime_config as rc
    from app.services import tiktok

    # Mock/offline mode: synthesize content locally — no yt-dlp / tikwm / network.
    if rc.get_value("ai_provider") == "mock":
        return _mock_payload(url)

    if tiktok.is_tiktok(url):
        info = tiktok.fetch(url, settings.tiktok_cookie)
        return {"media": info.get("media"), "images": info.get("images") or [],
                "caption": info.get("caption", ""), "author": info.get("author", ""),
                "source": "tiktok", "reach": info.get("reach", {})}
    media, caption, author, reach = fetch_url(url)
    return {"media": media, "images": [], "caption": caption, "author": author,
            "source": platform_from_url(url), "reach": reach}


def _mock_payload(url: str) -> dict:
    """Offline stand-in for a downloaded clip (AI_PROVIDER=mock). No network.

    A small synthetic image + a keyword-rich caption so the pipeline produces a
    realistic, non-trivial risk + reach without touching any external API.
    A configurable delay makes the analysis feel like real processing on the demo.
    """
    import time

    from app.services import runtime_config as rc
    try:
        delay = float(rc.get_value("mock_delay_seconds"))
    except Exception:  # noqa: BLE001 — missing/invalid -> no delay (keeps tests fast)
        delay = 0.0
    if delay > 0:
        time.sleep(delay)

    author = "demo_invest" if "instagram" not in (url or "") else "demo_reels"
    caption = (
        "Закрытый инвест-клуб: вложи и получай гарантированный доход 300% в месяц! "
        "Срочно, успей — реферальный бонус за друга. Подпишись на телеграм @invest_vip, "
        "ставки и казино, перевод USDT на кошелёк. Лицензии нет."
    )
    # 1x1 JPEG (smallest valid) — gives the pipeline a frame without a real download.
    img = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300"
        "0806060706050807070709090a0c140d0c0b0b0c1912130f14"
        "1d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c303134"
        "3434341f27393d38323c2e333432ffc0000b080001000101011100ffc4"
        "001f0000010501010101010100000000000000000102030405060708090a0bffda0008010100003f00d2cf20ffd9"
    )
    return {
        "media": None, "images": [img], "caption": caption,
        "author": author, "source": platform_from_url(url) if "http" in (url or "") else "mock",
        "reach": {"views": 327000, "likes": 14500, "comments": 530, "shares": 1900},
    }
