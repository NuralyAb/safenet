"""Autonomous fraud hunter — the system goes looking for schemes itself.

Instead of waiting for an analyst to paste a link, the hunter generates suspicious
SEARCH QUERIES (LLM-picked in openai/local, a curated seed list in mock) and fires
them through the existing keyword-discovery pipeline (discover_content → collect →
risk → score). High-risk hits surface in Materials/Radar and raise alerts on their
own. This drives our PROACTIVE discovery — not a browser scrolling TikTok.
"""
from __future__ import annotations

import json

# Curated hunting seed queries (used in mock, and as a fallback) — the three SafeNet KZ
# tracks in Russian and Kazakh: paid giveaways, hidden casino promotion, pyramids.
_SEED_QUERIES = [
    "розыгрыш номер 1000 тг каспи рандомайзер",
    "ұтыс ойыны қатысу ақылы каспи",
    "гив платный вход номера проданы",
    "как я поднял за вечер промокод ссылка в шапке",
    "занос недели слоты стрим промокод",
    "lucky jet сигналы бот бесплатно",
    "вложи 5000 получи 10000 каспи",
    "кепілдендірілген табыс салым досыңды шақыр",
    "пассивный доход 3% в день куратор",
    "инвест клуб закрытый чат выплаты скрин",
]

_SYS = (
    "Ты — аналитик SafeNet KZ. Сгенерируй поисковые запросы для поиска в соцсетях Казахстана "
    "ПРИЗНАКОВ: розыгрышей с платным участием (взнос, номера, Kaspi, рандомайзер), скрытой "
    "рекламы онлайн-казино (мой выигрыш, промокод, зеркало, стрим, сигналы Lucky Jet/Aviator) "
    "и финансовых пирамид (вложи–получи, % в день, рефералы, кураторы). Смешивай русский и "
    "казахский, сленг. Верни СТРОГО JSON-массив строк, без пояснений."
)
_ADAPT_SYS = (
    "Ты — аналитик-охотник за финансовым мошенничеством. По УЖЕ найденным паттернам "
    "(теги, telegram-каналы, домены подозрительных роликов) предложи НОВЫЕ поисковые "
    "запросы, чтобы найти БОЛЬШЕ связанного мошенничества той же сети/схемы. "
    "Верни СТРОГО JSON-массив строк, без пояснений."
)
SOURCES = ["youtube", "tiktok", "instagram"]


def _adapt_mock(tags: set[str], tg: set[str], dom: set[str], n: int) -> list[str]:
    """Deterministic follow-up queries derived from observed fraud patterns."""
    out: list[str] = []
    for h in list(tg)[:3]:
        out.append(f"{h} телеграм инвест сигналы")
    for d in list(dom)[:2]:
        out.append(f"{d} отзывы развод")
    for t in tags:
        if any(k in t for k in ("casino", "казино", "ставк", "slot", "рулет", "покер")):
            out.append(f"{t} без лицензии промокод")
    for q in _SEED_QUERIES:                       # pad with not-yet-used seeds
        out.append(q)
    seen: set[str] = set()
    res: list[str] = []
    for q in out:
        if q and q not in seen:
            seen.add(q)
            res.append(q)
    return res[:n]


def adapt_queries(session, n: int = 6) -> list[str]:
    """Next-round queries: learn from high-risk hits already found (their tags /
    telegram / domains) and search for more of the same network. Falls back to seeds."""
    from app.services import runtime_config as rc
    from app.db.models import Content, ContentRisk
    from app.services.extract import extract_identifiers

    try:
        rows = (session.query(ContentRisk).filter(ContentRisk.score >= 65)
                .order_by(ContentRisk.updated_at.desc()).limit(12).all())
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return generate_queries(n)

    cids = [r.content_id for r in rows]
    contents = {c.id: c for c in session.query(Content).filter(Content.id.in_(cids)).all()}
    tags: set[str] = set()
    tg: set[str] = set()
    dom: set[str] = set()
    for r in rows:
        c = contents.get(r.content_id)
        if not c:
            continue
        for t in (c.tags or []):
            tags.add(str(t).lower())
        ids = extract_identifiers(" ".join(filter(None, [c.transcript, c.ocr_text])))
        tg.update(ids["telegram"])
        dom.update(ids["domains"])

    if rc.get_value("ai_provider") == "mock" or bool(rc.get_value("mock_hunter")):
        return _adapt_mock(tags, tg, dom, n)
    try:
        from app.services.ai.factory import get_llm
        ctx = f"теги={sorted(tags)[:8]}, telegram={sorted(tg)[:6]}, домены={sorted(dom)[:6]}"
        raw = get_llm().complete(_ADAPT_SYS, f"Паттерны: {ctx}. Дай {n} НОВЫХ запросов JSON-массивом.") or ""
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1:
            arr = json.loads(raw[start:end + 1])
            qs = [str(q).strip() for q in arr if str(q).strip()]
            if qs:
                return qs[:n]
    except Exception:  # noqa: BLE001
        pass
    return _adapt_mock(tags, tg, dom, n) or generate_queries(n)


def generate_queries(n: int = 6) -> list[str]:
    """Pick hunting queries — LLM when available, else the curated seed list."""
    from app.services import runtime_config as rc

    if rc.get_value("ai_provider") == "mock" or bool(rc.get_value("mock_hunter")):
        return _SEED_QUERIES[:n]
    try:
        from app.services.ai.factory import get_llm
        raw = get_llm().complete(_SYS, f"Дай {n} запросов JSON-массивом.") or ""
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1:
            arr = json.loads(raw[start:end + 1])
            qs = [str(q).strip() for q in arr if str(q).strip()]
            if qs:
                return qs[:n]
    except Exception:  # noqa: BLE001 — LLM down/parse fail -> curated fallback
        pass
    return _SEED_QUERIES[:n]


# Synthetic findings with explicit facts → a controlled, believable risk spread
# (CRITICAL → LOW incl. a clean control). (caption, reach, facts, scheme_matches, related).
_F = ("promises_returns", "has_referral", "has_license", "gambling_content",
      "aggressive_investment", "hidden_engagement")
_HUNT_CLIPS = [
    ("Вложи 100$ — получай 1000$ каждый день! Реферальный бонус. Казино+инвест, пиши в ЛС @invest_vip",
     {"views": 812000, "likes": 41000, "comments": 1200, "shares": 5400},
     dict(zip(_F, (True, True, False, True, True, True))), 8, 20),
    ("Гарантированный доход 300% в месяц — успей вписаться! Приглашай друзей, t.me/profit_vip",
     {"views": 540000, "likes": 23000, "comments": 700, "shares": 2100},
     dict(zip(_F, (True, True, False, False, True, True))), 5, 12),
    ("Лучшее онлайн-казино без лицензии: джекпот, ставки 24/7, бонус по промокоду",
     {"views": 327000, "likes": 14500, "comments": 530, "shares": 1900},
     dict(zip(_F, (True, True, False, True, False, False))), 4, 6),
    ("Крипто-сигналы, приватный VIP-канал, заходи — реферальная программа",
     {"views": 96000, "likes": 4200, "comments": 180, "shares": 600},
     dict(zip(_F, (False, True, False, False, False, True))), 2, 3),
    ("Обзор новой кофейни в центре города, делюсь впечатлениями о завтраке",
     {"views": 8200, "likes": 210, "comments": 24, "shares": 6},
     dict(zip(_F, (False, False, True, False, False, False))), 0, 0),
]


# Real, openable clips the hunter is primed to surface. Unlike _HUNT_CLIPS (which use
# .example URLs and only feed Materials/graph), these carry REAL urls so they pass the
# frontend "real clip" filter and appear in the progressive hunt feed with a working
# "открыть видео" link. Facts are curated to give a believable CRITICAL→MEDIUM spread.
# (url, source, author, caption, reach, facts, scheme_matches, related)
_REAL_TARGETS = [
    ("https://www.instagram.com/reel/DZ9qsy1u9FY76TeA1pPpYzDiI-DTRSnvEqsn-40/",
     "instagram", "@profit_invest_pro",
     "Вложи 100$ — выводи 1000$ каждый день! Казино+инвест, реферальный бонус, пиши в ЛС",
     {"views": 740000, "likes": 38000, "comments": 1100, "shares": 4800},
     dict(zip(_F, (True, True, False, True, True, True))), 8, 18),
    ("https://www.youtube.com/watch?v=AHIo-JE-8pU",
     "youtube", "@money_machine_yt",
     "Гарантированный пассивный доход 300% в месяц — приглашай друзей, забирай бонусы",
     {"views": 512000, "likes": 21000, "comments": 640, "shares": 1900},
     dict(zip(_F, (True, True, False, False, True, True))), 5, 12),
    ("https://youtu.be/fhnwmlhV83A",
     "youtube", "@casino_jackpot_live",
     "Онлайн-казино без лицензии: джекпот, ставки 24/7, бонус по промокоду на депозит",
     {"views": 286000, "likes": 12400, "comments": 470, "shares": 1500},
     dict(zip(_F, (True, False, False, True, False, True))), 4, 7),
    ("https://vt.tiktok.com/ZSCYN71WM/",
     "tiktok", "@crypto_signals_vip",
     "Приватные крипто-сигналы, VIP-канал, реферальная программа — заходи зарабатывать",
     {"views": 198000, "likes": 9100, "comments": 320, "shares": 880},
     dict(zip(_F, (True, True, False, False, True, False))), 5, 9),
    ("https://vt.tiktok.com/ZSCYNTFa5/",
     "tiktok", "@bet_win_24",
     "Лучшие ставки и слоты — заноси, удваивай! Бонус новичкам по промокоду",
     {"views": 124000, "likes": 6300, "comments": 210, "shares": 540},
     dict(zip(_F, (True, False, False, True, False, True))), 4, 5),
]


def seed_real_targets(session) -> int:
    """Upsert the curated REAL hunt targets (idempotent by URL) so the autonomous hunt
    surfaces actual openable videos in its feed, not just synthetic .example clips."""
    import hashlib

    from app.db.models import Content
    from app.db.risk_repo import upsert_content_risk
    from app.services.content_scoring import score_content

    created = 0
    for url, s, author, caption, reach, facts, matches, related in _REAL_TARGETS:
        cid = hashlib.sha256(url.encode("utf-8")).hexdigest()
        a = score_content(facts, text=caption, scheme_matches=matches, related_objects=related,
                          evidence_ids=[cid])
        upsert_content_risk(session, cid, a.score, a.threat_level.value, a.breakdown,
                            a.recommendation, author=author, source=s, url=url, reach=reach,
                            track=a.track, lang=a.language)
        row = session.get(Content, cid)
        if row is None:
            row = Content(id=cid, external_id=cid, sha256=cid)
            session.add(row)
        row.source, row.author, row.lang = s, author, "ru"
        row.url = url
        row.caption = caption
        row.promises_returns = bool(facts.get("promises_returns"))
        row.has_referral = bool(facts.get("has_referral"))
        row.has_license = bool(facts.get("has_license"))
        row.gambling_content = bool(facts.get("gambling_content"))
        created += 1
    session.commit()
    return created


def _hunt_synthetic(session, srcs: list[str], queries: list[str], limit: int) -> int:
    """Mock hunt: synthesize + score findings INLINE (no Celery, no network, no OpenAI).

    Used when mock_hunter is on (independent of ai_provider), so the autonomous hunt
    reliably surfaces accounts even on a live AI run. Writes ContentRisk + a Content
    row per finding (so it shows in Materials/Radar/Dossier).
    """
    import hashlib

    from app.db.models import Content
    from app.db.risk_repo import upsert_content_risk
    from app.services import dev_mock
    from app.services.content_scoring import score_content

    handles = dev_mock._MOCK_HANDLES
    created = 0
    n = max(1, min(limit, len(_HUNT_CLIPS)))
    for q in queries:
        qh = int(hashlib.sha256(q.encode("utf-8")).hexdigest()[:6], 16)
        for s in srcs:
            for i in range(n):
                caption, reach, facts, matches, related = _HUNT_CLIPS[i]
                cid = hashlib.sha256(f"{s}|{q}|{i}".encode("utf-8")).hexdigest()
                author = f"@{handles[(qh + i) % len(handles)]}_{qh % 900 + 100}"
                a = score_content(facts, text=caption, scheme_matches=matches, related_objects=related,
                                  evidence_ids=[cid])
                upsert_content_risk(session, cid, a.score, a.threat_level.value, a.breakdown,
                                    a.recommendation, author=author, source=s,
                                    url=f"https://{s}.example/{author}/clip{i}", reach=reach,
                                    track=a.track, lang=a.language)
                row = session.get(Content, cid)
                if row is None:
                    row = Content(id=cid, external_id=cid, sha256=cid)
                    session.add(row)
                row.source, row.author, row.lang = s, author, "ru"
                row.url = f"https://{s}.example/{author}/clip{i}"
                row.caption = caption
                row.promises_returns = bool(facts.get("promises_returns"))
                row.has_referral = bool(facts.get("has_referral"))
                row.has_license = bool(facts.get("has_license"))
                row.gambling_content = bool(facts.get("gambling_content"))
                created += 1
    session.commit()
    return created


def run_hunt(session=None, *, sources: list[str] | None = None, source: str = "",
             count: int = 6, limit: int = 4, adapt: bool = False) -> dict:
    """Launch the hunt across one or more sources.

    adapt=True → next-round queries learned from already-found high-risk patterns
    (the hunter adjusts itself); else fresh seed/LLM queries. When mock_hunter (or
    AI_PROVIDER=mock) is on, findings are synthesized + scored INLINE; otherwise each
    query fires real keyword-discovery (Celery) and results land asynchronously.
    """
    from app.services import runtime_config as rc

    srcs = [s for s in (sources or ([source] if source else SOURCES)) if s in SOURCES] or ["youtube"]
    queries = (adapt_queries(session, count) if (adapt and session is not None)
               else generate_queries(count))

    mock = False
    try:
        mock = rc.get_value("ai_provider") == "mock" or bool(rc.get_value("mock_hunter"))
    except Exception:  # noqa: BLE001
        pass

    if mock and session is not None:
        real = seed_real_targets(session)          # curated REAL openable videos only
        return {"started": True, "sources": srcs, "queries": queries,
                "count": len(queries), "adapted": bool(adapt),
                "found": real, "real": real, "mode": "mock"}

    from app.workers.tasks import ingest
    for q in queries:
        for s in srcs:
            ingest(s, q, kind="keyword", limit=limit)
    return {"started": True, "sources": srcs, "queries": queries,
            "count": len(queries), "adapted": bool(adapt), "mode": "live"}
