"""Dev/Mock mode — seed a self-contained demo around one Instagram reel.

Toggled from Settings (dev_mode). When ON it injects a fully-analysed reel
(DZ9qsy1u9FY) for account ami_d0maru — risk score, transcript/OCR with hard
identifiers, an account-level assessment, a watchlist entry + a fresh alert, and a
Telegram connections graph in Neo4j — WITHOUT needing an Instagram cookie or any
OpenAI call. When OFF it removes everything it created. Idempotent both ways.

This is demo/synthetic data only (the prototype rule): nothing real is collected.
"""
from __future__ import annotations

MOCK_AUTHOR = "ami_d0maru"
MOCK_CONTENT_ID = "devmock-DZ9qsy1u9FY"
MOCK_REEL_URL = "https://www.instagram.com/reels/DZ9qsy1u9FY/"

# Telegram channels + linked accounts that form the TG connections graph. Mock-unique
# ids so clearing them never touches real/seed graph nodes.
_TG = ["ami_invest_vip", "ami_signals"]
_WALLET = "0x2b44ebc7d5d308bd7f1cdf44ac892c23a565847a"
_DOMAIN = "crypto-invest.net"   # real, recently-registered → WHOIS shows a fresh-domain red flag
_PHONE = "+77011234567"
_LINKED = ["@crypto_ami", "@signals_pro_kz"]   # share a TG channel with the target

_TRANSCRIPT = (
    "Привет! Закрытый инвест-клуб ami_d0maru: вложи и получай 300% в месяц. "
    "Подписывайся на телеграм @ami_invest_vip, сигналы в @ami_signals. "
    "Перевод USDT на кошелёк " + _WALLET + ". Пиши/звони " + _PHONE + "."
)
_OCR = "crypto-invest.net • t.me/ami_invest_vip • ГАРАНТИЯ ДОХОДА 300%"

_FACTS = {
    "promises_returns": True, "has_referral": True, "has_license": False,
    "gambling_content": False, "aggressive_investment": True, "hidden_engagement": True,
}
_REACH = {"views": 412000, "likes": 21000, "comments": 880, "shares": 3400}


def _score():
    from app.services.content_scoring import score_content
    return score_content(_FACTS, scheme_matches=2, related_objects=len(_LINKED) + len(_TG),
                         evidence_ids=[MOCK_CONTENT_ID])


# Synthetic clips for offline collection (AI_PROVIDER=mock): a believable mix of
# casino / pyramid / referral content + one clean control. Keyword-rich so the
# mock LLM extracts real flags and the risk score varies per video.
_MOCK_CLIPS = [
    ("Вложи 100$ и получай 1000$ каждый день! Реферальный бонус за друга. Пиши в @invest_vip, кошелёк USDT.",
     {"views": 812000, "likes": 41000, "comments": 1200, "shares": 5400}),
    ("Лучшее онлайн-казино без лицензии — джекпот сегодня! t.me/casino_bot, ставки и слоты 24/7.",
     {"views": 540000, "likes": 23000, "comments": 700, "shares": 2100}),
    ("Срочно успей! Закрытый инвест-клуб, гарантированный доход 300% в месяц, переходи в личку.",
     {"views": 327000, "likes": 14500, "comments": 530, "shares": 1900}),
    ("Сигналы по крипте — заходи в приватный канал @signals_pro, профит каждый день, реферал.",
     {"views": 96000, "likes": 4200, "comments": 180, "shares": 600}),
    ("Обзор новой кофейни в центре города, делюсь впечатлениями о завтраке.",
     {"views": 8200, "likes": 210, "comments": 24, "shares": 6}),
]
# 1x1 JPEG seed — appended with a per-clip byte to get a distinct sha256 / content_id.
_MOCK_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909"
    "0a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c3031343434"
    "341f27393d38323c2e333432ffc0000b08000100010101 1100ffc4001f0000010501010101010100"
    "00000000000000000102030405060708090a0bffda0008010100003f00d2cf20ffd9".replace(" ", "")
)


# Plausible fraud-y account handles so each query surfaces DISTINCT "found" accounts.
_MOCK_HANDLES = ["invest_pro", "casino_vip", "crypto_signals", "fast_money_kz",
                 "bet_king", "profit_club", "x100_trader", "lucky_spin"]


def mock_collect(source: str, target: str, limit: int, store) -> list[dict]:
    """Offline stand-in for a collector run (AI_PROVIDER=mock) — NO yt-dlp / network.

    Synthesizes a few clips for the query/account `target`, each UNIQUE per
    (target, index) so different searches surface different accounts/videos (counts
    grow, authors look like real handles). Stored to local MinIO; the rest of the
    pipeline (mock AI → risk → score) runs unchanged.
    """
    import hashlib

    from app.services.extract import extract_identifiers

    qh = int(hashlib.sha256((target or "q").encode("utf-8")).hexdigest()[:6], 16)
    n = max(1, min(limit or 5, len(_MOCK_CLIPS)))
    out: list[dict] = []
    for i in range(n):
        caption, reach = _MOCK_CLIPS[i]
        # distinct bytes per (target, i) -> distinct sha256 / content_id
        media = _MOCK_JPEG + hashlib.sha256(f"{target}|{i}".encode("utf-8")).digest()[:6]
        ref = store.store(media, source, content_type="image/jpeg", ext="jpg")
        ids = extract_identifiers(caption)
        author = f"@{_MOCK_HANDLES[(qh + i) % len(_MOCK_HANDLES)]}_{qh % 900 + 100}"
        out.append({
            "content_id": ref.sha256, "source": source, "sha256": ref.sha256,
            "raw_key": ref.raw_key, "evidence_key": ref.evidence_key, "size": ref.size,
            "content_type": ref.content_type, "author": author,
            "url": f"https://{source}.example/{author}/clip{i}", "text": caption,
            "image": media, "reach": reach,
            "telegram": ids["telegram"], "wallets": ids["wallets"], "domains": ids["domains"],
        })
    return out


def seed_mock(session) -> dict:
    """Create the mock reel analysis + TG connections graph. Idempotent."""
    from app.db import notifications_repo as notif
    from app.db.models import Content
    from app.db.risk_repo import upsert_assessment, upsert_content_risk
    from app.services import watchlist

    a = _score()

    # 1) Monitored account (so the alert + dossier treat it as watched).
    watchlist.add_target(session, "instagram", "account", MOCK_AUTHOR, "dev-mock")

    # 2) Content row with retained transcript/OCR carrying the hard identifiers.
    row = session.get(Content, MOCK_CONTENT_ID)
    if row is None:
        row = Content(id=MOCK_CONTENT_ID, external_id=MOCK_CONTENT_ID, sha256=MOCK_CONTENT_ID)
        session.add(row)
    row.source = "instagram"
    row.author = MOCK_AUTHOR
    row.url = MOCK_REEL_URL
    row.lang = "ru"
    row.transcript = _TRANSCRIPT
    row.ocr_text = _OCR
    row.tags = ["деньги", "график", "telegram"]
    row.promises_returns, row.has_referral = True, True
    row.has_license, row.gambling_content = False, False
    session.commit()

    # 3) Per-video + account-level risk.
    upsert_content_risk(session, MOCK_CONTENT_ID, a.score, a.threat_level.value, a.breakdown,
                        a.recommendation, author=MOCK_AUTHOR, source="instagram",
                        url=MOCK_REEL_URL, reach=_REACH)
    upsert_assessment(session, MOCK_AUTHOR, a.score, a.threat_level.value, a.breakdown,
                      a.recommendation)

    # 4) Telegram connections graph in Neo4j (best-effort).
    _seed_graph()

    # 5) Fresh alert (so the toast fires immediately).
    notif.record_new_video(session, content_id=MOCK_CONTENT_ID, author=MOCK_AUTHOR,
                           source="instagram", url=MOCK_REEL_URL, score=a.score,
                           threat_level=a.threat_level.value)
    return {"seeded": True, "account": MOCK_AUTHOR, "score": a.score,
            "threat_level": a.threat_level.value}


def _seed_graph() -> None:
    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import Edge, GraphBuilder

        gb = GraphBuilder(neo4j_driver())
        gb.init_schema()
        prov = {"confidence": 1.0, "source": "dev-mock", "evidence_id": MOCK_CONTENT_ID, "ts": ""}
        # target → its TG channels / wallet / domain
        gb.link_identifiers(MOCK_AUTHOR, telegram=_TG, wallets=[_WALLET], domains=[_DOMAIN],
                            source="dev-mock")
        # linked accounts share the first TG channel → a visible connection cluster
        for acc in _LINKED:
            gb.upsert_edge(Edge("Account", acc, "MENTIONS", "Infrastructure",
                                f"tg:{_TG[0]}", dict(prov)))
        # SAME_PERSON candidate (unconfirmed) between the target and one linked account
        gb.upsert_edge(Edge("Account", MOCK_AUTHOR, "SAME_PERSON", "Account", _LINKED[0],
                            {**prov, "confidence": 0.8, "confirmed": False}))
    except Exception:  # noqa: BLE001 — graph is an enrichment, never block the toggle
        pass


def clear_mock(session) -> dict:
    """Remove everything seed_mock created. Idempotent."""
    from app.db.models import (Content, ContentRisk, Evidence, RiskAssessment,
                               WatchlistNotification, WatchTarget)

    for n in session.query(WatchlistNotification).filter_by(content_id=MOCK_CONTENT_ID).all():
        session.delete(n)
    for r in session.query(ContentRisk).filter_by(content_id=MOCK_CONTENT_ID).all():
        session.delete(r)
    for e in session.query(Evidence).filter_by(content_id=MOCK_CONTENT_ID).all():
        session.delete(e)
    c = session.get(Content, MOCK_CONTENT_ID)
    if c:
        session.delete(c)
    for ra in session.query(RiskAssessment).filter_by(target=MOCK_AUTHOR).all():
        session.delete(ra)
    for t in session.query(WatchTarget).filter_by(kind="account", value=MOCK_AUTHOR).all():
        session.delete(t)
    session.commit()
    _clear_graph()
    return {"cleared": True}


def _clear_graph() -> None:
    try:
        from app.db.clients import neo4j_driver

        ids = [MOCK_AUTHOR, *_LINKED, *(f"tg:{t}" for t in _TG), f"wallet:{_WALLET}", f"http:{_DOMAIN}"]
        with neo4j_driver().session() as s:
            s.run("UNWIND $ids AS id MATCH (n {id: id}) DETACH DELETE n", ids=ids)
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass
