"""SafeNet KZ demo data — synthetic accounts, posts and group chats (NO real people).

The accounts are wired into realistic NETWORKS through shared identifiers, so the
graph shows what the hackathon calls «аккаунты, каналы и домены как единая сеть»:
  * three «гив»-accounts collecting money to ONE Kaspi number (track 1)
  * casino «блогеры» pushing the SAME promo code / shortener domain (track 2)
  * a pyramid whose curators share ONE card and Telegram contact (track 3)
plus clean / hard-negative posts so the queue also shows what is NOT flagged.

All texts are synthetic. Seeding is idempotent (content ids derive from the text)
and only touches rows whose url starts with DEMO_URL.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
DEMO_URL = "https://safenet.demo/"

DEMO_CHATS = {
    "pyramid_telegram": ("demo_pyramid_telegram.json", "Telegram: «BEREKE INVEST | Закрытый клуб» (пирамида)"),
    "lottery_whatsapp": ("demo_lottery_whatsapp.txt", "WhatsApp: «Гив Шымкент» (платные розыгрыши)"),
}

_KASPI_GIV = "+7 747 123 45 67"
_CARD_PYR = "4400 4301 2345 6789"

# (author, platform, text, views)
DEMO_POSTS: list[tuple[str, str, str, int]] = [
    # --- track 1: paid giveaways, one Kaspi number behind three accounts
    ("giv_shymkent", "instagram", f"🎁 РОЗЫГРЫШ iPhone 16 Pro! Номер = 1000 тг, всего 150 номеров. Оплата на Kaspi {_KASPI_GIV}. Как только раскупят — крутим рандомайзер в прямом эфире", 48200),
    ("giv_shymkent", "instagram", f"Розыгрыш №28 — 200 000 тг! Номер по 2000 тг, осталось 37 номеров. Kaspi {_KASPI_GIV}", 39100),
    ("aruzhan_givs", "instagram", f"Ұтыс ойыны! Бас жүлде — алтын сақина 💍 Бір нөмір 1500 тг, Kaspi-ге аударыңыз {_KASPI_GIV}. Жеңімпазды тікелей эфирде кездейсоқ анықтаймыз", 22800),
    ("lucky_nomer_kz", "tiktok", f"ЛОТО-ГИВ 💎 Билетик всего 500₸! Колесо крутим в субботу на стриме. Номерок бронируем в директе, оплата {_KASPI_GIV}", 131000),
    ("lucky_nomer_kz", "tiktok", "Р О З Ы Г Р Ы Ш 🎁 вход 1000тг на k@spi, победителя выберет колесо. Каждую пятницу новый тур!", 87400),
    # --- track 2: hidden casino ads, shared promo + shortener domain
    ("dana_lifestyle", "instagram", "Друзья, вот так выглядит мой вечер пятницы 😎 +250 000 ₸ за пару часов. Хочешь так же — смотри закреп в профиле, промокод SHYM777", 312000),
    ("dana_lifestyle", "instagram", "Как я подняла 420к за неделю 🙈 всё рассказываю в телеге t.me/dana_bonus_kz, промокод SHYM777", 276000),
    ("streamer_azamat", "tiktok", "Ночной стрим: Gates of Olympus, заносы недели! Регистрация по ссылке cutt.ly/kz-slots даёт +150% к депозиту, промо SHYM777", 940000),
    ("streamer_azamat", "tiktok", "Лаки Джет даёт иксы! Бот с сигналами — t.me/luckybot_kz, первые 3 дня бесплатно. Ссылка в шапке", 615000),
    ("kz_bet_signals", "telegram", "Сигналы Aviator на сегодня 🚀 Рабочее зеркало: cutt.ly/kz-slots — без VPN, фриспины новичкам", 18400),
    ("qazaq_utys_kz", "instagram", "Бүгін казинода 300 мың ұттым! 💰 Промокод: SHYM777, сілтеме профильде", 55600),
    ("bonus_man_kz", "youtube", "Kak ya podnyal 500k v kazino za vecher, promokod SHYM777, ssylka v profile", 74300),
    # --- track 3: pyramid, curators share a card and the same Telegram
    ("bereke_invest", "telegram", f"Инвест-клуб «Береке»: доход 3% в день, выплаты по пятницам на Kaspi. Переводы на карту {_CARD_PYR}. Пригласи друга — 10% с его вклада!", 9800),
    ("kurator_aigerim", "instagram", f"Девочки, я уже третий месяц в проекте 🙌 вложила 50 000, вывожу по 15 000 каждую неделю. Скрины выплат в сторис. Пишите @bereke_kurator, карта {_CARD_PYR}", 41200),
    ("kurator_erzhan", "whatsapp", "Вложи 20 000 тг — через 14 дней получишь 60 000! Гарантированный доход, осталось 4 места. Пишите куратору @bereke_kurator", 6100),
    ("aru_profit", "instagram", "5000 тг салсаңыз, бір аптада 10 000 тг аласыз! Кепілдендірілген табыс. Досыңды шақыр — бонус. Асығыңыз, 3 орын қалды", 26700),
    ("aru_profit", "instagram", "Гaрaнтирoвaнный дoхoд 40% в месяц, перевод на карту. Чем больше структура — тем выше доход 💸 @bereke_kurator", 19300),
    # --- clean / hard negatives (must NOT be flagged)
    ("salon_ayla", "instagram", "РОЗЫГРЫШ! 🎁 Дарим сертификат на 20 000 тг. Условия: подписка, лайк, отметь подругу. Участие бесплатное, итоги в пятницу через рандомайзер", 15400),
    ("halyk_news", "instagram", "Депозит «Онлайн» до 15% годовых. Вклады гарантированы КФГД. Откройте в Homebank", 88000),
    ("shymkent_news", "telegram", "Полиция Шымкента задержала организаторов финансовой пирамиды: обещали 30% в месяц, ущерб — 300 млн тг. Не переводите деньги незнакомцам", 132000),
    ("sport_kz", "telegram", "Финал Лиги чемпионов: букмекеры называют фаворитом «Реал», коэффициент 1.9", 47000),
    ("mama_aruzhan", "whatsapp", "Сбор на операцию для Даниала: Kaspi 4400 4301 9876 5437, любая сумма. Отчёт выложим", 3200),
    ("arzan_shop", "instagram", "Распродажа! Скидки до 50% только сегодня, успейте — осталось 10 пар. Оплата Kaspi QR", 12700),
    ("chess_club", "instagram", "Шахматный турнир: взнос 2000 тг, призовой фонд распределяется между призерами", 2100),
]


def demo_chat_bytes(name: str) -> tuple[bytes, str]:
    fname, _ = DEMO_CHATS[name]
    return (DATA / fname).read_bytes(), fname


def demo_chat_list() -> list[dict]:
    return [{"id": k, "file": v[0], "title": v[1]} for k, v in DEMO_CHATS.items()]


def _cid(author: str, text: str) -> str:
    return hashlib.sha256(f"safenet-demo|{author}|{text}".encode("utf-8")).hexdigest()


def rescore_all(session) -> dict:
    """Re-score every queued material with the SafeNet engine from its retained text.

    Rows scored by the previous engine (e.g. level CRITICAL, no track) get the
    per-track score, quotes and 3-level scale. The analyst disposition is kept.
    Group-chat rows are left as they are (their score comes from the chat analysis).
    """
    from app.db.models import Content, ContentRisk
    from app.services.content_scoring import score_content
    from app.services.safenet import detect

    rows = session.query(ContentRisk).all()
    contents = {c.id: c for c in session.query(Content).filter(
        Content.id.in_([r.content_id for r in rows])).all()} if rows else {}
    done = 0
    for r in rows:
        if r.source in ("telegram_group", "whatsapp_group", "chat"):
            continue
        c = contents.get(r.content_id)
        segments = [(k, v) for k, v in (("caption", c.caption if c else ""),
                                        ("transcript", c.transcript if c else ""),
                                        ("ocr", c.ocr_text if c else "")) if v]
        if not segments:
            continue
        det = detect(segments, vision_tags=(c.tags or []) if c else None)
        a = score_content(safenet=det.to_dict(), evidence_ids=[r.content_id],
                          has_license=bool(c.has_license) if c else False)
        from app.services.content_scoring import priority_from
        r.score, r.threat_level, r.breakdown = a.score, a.threat_level.value, a.breakdown
        r.recommendation, r.track, r.lang = a.recommendation, a.track, a.language
        r.priority = priority_from(a.score, r.views)
        done += 1
    session.commit()
    return {"rescored": done, "total": len(rows)}


def seed(session, *, reset: bool = False) -> dict:
    """Write the demo posts (+ both demo chats) into content / content_risk / graph."""
    from app.db.models import Content, ContentRisk
    from app.db.risk_repo import upsert_content_risk
    from app.services.content_scoring import score_content
    from app.services.safenet import detect

    if reset:
        old = [r.content_id for r in session.query(ContentRisk).filter(ContentRisk.url.like(f"{DEMO_URL}%"))]
        if old:
            session.query(ContentRisk).filter(ContentRisk.content_id.in_(old)).delete(synchronize_session=False)
            session.query(Content).filter(Content.id.in_(old)).delete(synchronize_session=False)
            session.commit()

    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import GraphBuilder
        graph = GraphBuilder(neo4j_driver())
    except Exception:  # noqa: BLE001
        graph = None

    created, flagged = 0, 0
    for author, platform, text, views in DEMO_POSTS:
        cid = _cid(author, text)
        det = detect([("caption", text)])
        a = score_content(safenet=det.to_dict(), evidence_ids=[cid])
        url = f"{DEMO_URL}{platform}/{author}/{cid[:10]}"
        upsert_content_risk(session, cid, a.score, a.threat_level.value, a.breakdown, a.recommendation,
                            author=author, source=platform, url=url,
                            reach={"views": views, "likes": views // 25, "comments": views // 300,
                                   "shares": views // 500},
                            track=a.track, lang=a.language)
        row = session.get(Content, cid)
        if row is None:
            row = Content(id=cid, external_id=cid, sha256=cid)
            session.add(row)
        row.source, row.author, row.url, row.lang, row.caption = platform, author, url, a.language or "ru", text
        row.promises_returns = det.has("pyramid.unrealistic_return") or det.has("pyramid.recruitment_income")
        row.has_referral = det.has("pyramid.referral")
        row.gambling_content = det.has("casino.gambling") or det.has("casino.brand")
        session.commit()
        if graph is not None:
            ids = det.identifiers
            try:
                graph.link_identifiers(author, telegram=ids.get("telegram", []), domains=ids.get("domains", []),
                                       phones=ids.get("phones", []), cards=ids.get("cards", []),
                                       promo_codes=ids.get("promo_codes", []),
                                       short_links=ids.get("short_links", []), source="demo")
            except Exception:  # noqa: BLE001 — graph is best-effort (neo4j down)
                graph = None
        created += 1
        flagged += a.score >= 40

    chats = []
    for name in DEMO_CHATS:
        from app.api.v1.analyze import _persist_group
        from app.services.safenet.group import analyze_chat, parse_chat

        raw, fname = demo_chat_bytes(name)
        cid = hashlib.sha256(raw).hexdigest()
        result = analyze_chat(parse_chat(raw, fname), evidence_ids=[cid])
        _persist_group(session, result, raw, cid)
        session.query(ContentRisk).filter_by(content_id=cid).update({"url": f"{DEMO_URL}chat/{name}"})
        session.query(Content).filter_by(id=cid).update({"url": f"{DEMO_URL}chat/{name}"})
        session.commit()
        chats.append({"name": name, "score": result["risk"]["score"], "track": result["risk"]["track"]})
    return {"posts": created, "flagged": flagged, "chats": chats, "graph": graph is not None}
