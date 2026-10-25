"""Seed demo data for the prototype.

IMPORTANT: synthetic data only — this is what makes it safe to route through
external AI APIs during prototyping (see CLAUDE.md / PROTOTYPE_ROADMAP.md).

Creates:
  - one analyst (argon2 password + TOTP secret) — prints the otpauth URI to enrol
  - a small fraud network in Neo4j: two accounts sharing a wallet + telegram
    (so the graph shows a real cluster), plus a SAME_PERSON candidate
  - matching fingerprints in Qdrant (shared hard identifiers -> likely_same_scheme)

Run:  python -m scripts.seed_demo
Idempotent: re-running does not duplicate the user or nodes.
"""
from __future__ import annotations

import os
import secrets

import pyotp
from sqlalchemy.orm import Session

from app.core.config import Role, settings
from app.core.security import hash_password
from app.db.models import User

DEMO_USER = "analyst-1"
# Synthetic demo credential — local prototype only. Never a literal in source
# (SAST gate): take it from the environment, or mint a fresh random one per run
# and print it on creation for TOTP enrolment.
DEMO_PASSWORD = os.environ.get("AFM_DEMO_PASSWORD") or secrets.token_urlsafe(12)


def seed_user(session: Session, username: str = DEMO_USER,
              password: str = DEMO_PASSWORD, role: Role = Role.ANALYST) -> dict:
    """Create the demo analyst, or reset its password/role if it already exists.

    Idempotent AND deterministic: re-seeding with a known AFM_DEMO_PASSWORD always
    yields the same login, so a demo machine has reproducible credentials (the TOTP
    secret is preserved so an already-enrolled authenticator keeps working)."""
    existing = session.query(User).filter_by(username=username).one_or_none()
    if existing is not None:
        existing.password_hash = hash_password(password)
        existing.role = role.value
        session.commit()
        return {"username": username, "password": password,
                "totp_secret": existing.totp_secret,
                "otpauth": pyotp.TOTP(existing.totp_secret).provisioning_uri(
                    name=username, issuer_name="AFM"),
                "created": False}

    secret = pyotp.random_base32()
    session.add(User(
        username=username, role=role.value,
        password_hash=hash_password(password), totp_secret=secret,
    ))
    session.commit()
    return {
        "username": username,
        "password": password,
        "totp_secret": secret,
        "otpauth": pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="AFM"),
        "created": True,
    }


# --- fraud network (Neo4j + Qdrant) ------------------------------------------
# @fast_profit & @invest_money share wallet USDT-X and telegram @fastmoney
# -> one scheme scaling across accounts. @crypto_x100 shares only the wallet.
_ACCOUNTS = ["@fast_profit", "@invest_money", "@crypto_x100"]
_WALLET = "wallet:USDT-X"
_TELEGRAM = "tg:fastmoney"
# A REAL public Ethereum address (demo data, not a real case) that has on-chain
# transfers to a known exchange. Attaching it to a seed account makes the Money
# Flow tab trace account → wallet → Binance on live chain data via Etherscan V2.
_REAL_WALLET = "wallet:0x2b44ebc7d5d308bd7f1cdf44ac892c23a565847a"


def seed_content(session) -> None:
    """Content rows with NLP claim flags + retained transcript/OCR carrying real hard
    identifiers (Telegram / wallet / phone), so the Target Dossier shows a full portrait
    and the identifier extraction has something to find. Upserts so re-seeding refreshes."""
    from app.db.models import Content

    # (id, author, url, transcript, ocr_text, [promises, referral, license, gambling])
    rows = [
        ("seed-fp-1", "@fast_profit", "https://youtu.be/seed-fp-1",
         "Вложи 100 долларов и получай 1000 каждый день. Пиши мне в телеграм @fastmoney, "
         "переводи USDT на кошелёк 0x2b44ebc7d5d308bd7f1cdf44ac892c23a565847a. Пригласи друга — бонус!",
         "ПОДПИШИСЬ t.me/fastmoney • WhatsApp +7 701 234 56 78 • profit-x.com",
         [True, True, False, False]),
        ("seed-fp-2", "@fast_profit", "https://youtu.be/seed-fp-2",
         "Закрытый клуб инвесторов, доходность 300% в месяц гарантирую. Канал @fastmoney, "
         "звони +7 701 234 56 78, кошелёк тот же 0x2b44ebc7d5d308bd7f1cdf44ac892c23a565847a.",
         "VIP сигналы t.me/fastmoney",
         [True, True, False, False]),
        ("seed-im-1", "@invest_money", "https://youtu.be/seed-im-1",
         "Гарантированный доход без риска, 100% заработок. Подключайся в @fastmoney.",
         "t.me/fastmoney",
         [True, False, False, False]),
    ]
    for cid, author, url, transcript, ocr, (pr, ref, lic, gam) in rows:
        row = session.get(Content, cid)
        if row is None:
            row = Content(id=cid, external_id=cid, sha256="0" * 64)
            session.add(row)
        row.source = "seed"
        row.author = author
        row.url = url
        row.lang = "ru"
        row.transcript = transcript
        row.ocr_text = ocr
        row.promises_returns, row.has_referral, row.has_license, row.gambling_content = pr, ref, lic, gam
    session.commit()


def seed_content_risk(session) -> None:
    """Per-VIDEO risk scores so the «Материалы» triage isn't empty before any run.

    Scored with the SAME deterministic engine the pipeline uses (content_scoring),
    so the demo reflects real graded per-video output (incl. the two new patterns).
    """
    from app.db.risk_repo import upsert_content_risk
    from app.services.content_scoring import score_content

    # (content_id, author, source, url, facts, scheme_matches, related_objects, reach)
    rows = [
        ("seed-fp-1", "@fast_profit", "youtube", "https://youtu.be/seed-fp-1",
         {"promises_returns": True, "has_referral": True, "has_license": False,
          "gambling_content": False, "aggressive_investment": True, "hidden_engagement": True},
         2, 4, {"views": 184000, "likes": 9100, "comments": 420, "shares": 1300}),
        ("seed-fp-2", "@fast_profit", "youtube", "https://youtu.be/seed-fp-2",
         {"promises_returns": True, "has_referral": True, "has_license": False,
          "gambling_content": False, "aggressive_investment": True, "hidden_engagement": False},
         2, 3, {"views": 52000, "likes": 3100, "comments": 110, "shares": 280}),
        ("seed-im-1", "@invest_money", "youtube", "https://youtu.be/seed-im-1",
         {"promises_returns": True, "has_referral": False, "has_license": False,
          "gambling_content": False, "aggressive_investment": False, "hidden_engagement": False},
         1, 2, {"views": 31000, "likes": 1200, "comments": 60, "shares": 90}),
        ("seed-cx-1", "@crypto_x100", "tiktok", "https://tiktok.com/@crypto_x100/video/seed-cx-1",
         {"promises_returns": False, "has_referral": False, "has_license": False,
          "gambling_content": True, "aggressive_investment": False, "hidden_engagement": False},
         0, 1, {"views": 8000, "likes": 300, "comments": 20, "shares": 15}),
    ]
    for cid, author, source, url, facts, matches, related, reach in rows:
        a = score_content(facts, scheme_matches=matches, related_objects=related,
                          evidence_ids=[cid])
        upsert_content_risk(session, cid, a.score, a.threat_level.value, a.breakdown,
                            a.recommendation, author=author, source=source, url=url, reach=reach)


def seed_watchlist(session) -> None:
    """Sample monitoring targets so the Мониторинг screen isn't empty."""
    from app.services.watchlist import add_target

    add_target(session, "youtube", "account", "@fast_profit", "seed")
    add_target(session, "youtube", "keyword", "инвест казино без лицензии", "seed")


def seed_assessments(session) -> None:
    """Sample risk assessments so the Триаж queue isn't empty before any investigation."""
    from app.db.risk_repo import upsert_assessment

    rows = [
        ("@fast_profit", 84, "HIGH", "Передать на ручную проверку",
         [{"factor": "financial_promises", "contribution": 25, "note": "обещание прибыли"}]),
        ("@invest_money", 65, "HIGH", "Передать на ручную проверку",
         [{"factor": "referral_structure", "contribution": 20, "note": "реферальная система"}]),
        ("@crypto_x100", 38, "LOW", "Наблюдение",
         [{"factor": "suspicious_links", "contribution": 15, "note": "связанные объекты"}]),
    ]
    for target, score, level, rec, breakdown in rows:
        upsert_assessment(session, target, score, level, breakdown, rec)


def seed_graph(driver) -> None:
    from app.services.graph_builder import Edge, GraphBuilder

    gb = GraphBuilder(driver)
    gb.init_schema()
    prov = {"confidence": 1.0, "source": "seed", "evidence_id": "seed", "ts": "2026-06-22T00:00:00Z"}
    for acc in _ACCOUNTS:
        gb.upsert_edge(Edge("Account", acc, "MENTIONS", "Infrastructure", _WALLET, dict(prov)))
    for acc in _ACCOUNTS[:2]:
        gb.upsert_edge(Edge("Account", acc, "MENTIONS", "Infrastructure", _TELEGRAM, dict(prov)))
    # Attach the real on-chain wallet to one account so Money Flow traces to a real
    # exchange (account → wallet → Binance) instead of stopping at the stub wallet.
    gb.upsert_edge(Edge("Account", _ACCOUNTS[0], "MENTIONS", "Infrastructure", _REAL_WALLET, dict(prov)))
    # SAME_PERSON candidate (unconfirmed) between the two telegram-sharing accounts
    gb.upsert_edge(Edge("Account", _ACCOUNTS[0], "SAME_PERSON", "Account", _ACCOUNTS[1],
                        {**prov, "confidence": 0.82, "confirmed": False}))


def _fake_vec(seed: int, dim: int) -> list[float]:
    # deterministic non-zero vector (matching wins on hard identifiers, not these)
    return [((seed * 7 + i) % 97) / 97.0 for i in range(dim)]


def seed_fingerprints(client) -> None:
    from app.services.fingerprint import Fingerprint, FingerprintStore

    store = FingerprintStore(client)
    store.init_collection()
    for i, acc in enumerate(_ACCOUNTS):
        fp = Fingerprint(
            content_id=f"seed-{i}", author=acc,
            vectors={"text": _fake_vec(i, settings.dim_text)},
            telegram=["fastmoney"] if i < 2 else [],
            wallets=["USDT-X"],
        )
        store.upsert(fp)


def seed_demo_network(session, driver, client) -> None:
    """Populate a small synthetic fraud network across all stores so every screen
    has something to show on stage — incl. a REAL on-chain wallet so Money Flow
    traces account → wallet → Binance live. Opt-in (--with-demo-network) so the
    default seed stays «no mock data»."""
    seed_content(session)
    seed_content_risk(session)
    seed_assessments(session)
    seed_watchlist(session)
    seed_graph(driver)
    seed_fingerprints(client)
    print("DEMO NETWORK SEEDED — accounts:", ", ".join(_ACCOUNTS))
    print("  Money Flow: open «Сеть → Money Flow», trace @fast_profit "
          "→ wallet 0x2b44…847a → Binance (live on-chain).")


def main() -> None:
    import argparse

    from app.db.clients import neo4j_driver, qdrant_client
    from app.db.session import get_session

    parser = argparse.ArgumentParser(description="Seed demo data for the prototype.")
    parser.add_argument("--with-demo-network", action="store_true",
                        help="Also seed a synthetic fraud network (graph/fingerprints/"
                             "risk) for a full stage demo. Default: users only.")
    flags = parser.parse_args()

    # Default: ONLY the operator accounts (you must have a user to log in).
    # No fraud/demo data — everything else comes from real collection/analysis.
    gen = get_session()
    session = next(gen)
    try:
        info = seed_user(session)
        print("ANALYST:", {k: info[k] for k in info if k != "otpauth"})
        if info.get("otpauth"):
            print("ENROL TOTP:", info["otpauth"])

        sup = seed_user(session, username="supervisor-1",
                        password=secrets.token_urlsafe(12), role=Role.SUPERVISOR)
        print("SUPERVISOR:", {k: sup[k] for k in sup if k != "otpauth"})
        if sup.get("otpauth"):
            print("ENROL TOTP (supervisor):", sup["otpauth"])

        if flags.with_demo_network:
            seed_demo_network(session, neo4j_driver(), qdrant_client())
        else:
            print("USERS SEEDED — no demo fraud data. "
                  "Add accounts via «Мониторинг»/«Анализ видео», "
                  "or run with --with-demo-network for a full stage demo.")
    finally:
        gen.close()


if __name__ == "__main__":
    main()
