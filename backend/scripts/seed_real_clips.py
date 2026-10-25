"""Seed REAL public YouTube clips for the demo — no OpenAI, no biometrics.

Pulls real public videos via yt-dlp (metadata only: id/title/channel/views), then
scores each one DETERMINISTICALLY from facts read off its REAL title (so the score
is grounded in what the video itself claims and traces to the title as evidence —
an educational clip scores LOW, a "гарантия 300%" clip scores HIGH). Persists a
Content + ContentRisk row per clip so the Live-scan feed / materials show genuine,
clickable videos with real thumbnails.

This is metadata-only display data: no media is downloaded, nothing is sent to an
external AI, and the risk is an illustrative title-level signal — NOT a full
analysis or a legal verdict.

Run:    docker compose exec backend python -m scripts.seed_real_clips
Clear:  docker compose exec backend python -m scripts.seed_real_clips --clear
"""
from __future__ import annotations

import hashlib
import subprocess
import sys

ID_PREFIX = "realyt-"

# Scam-pattern queries (+ a couple neutral controls) → ~50 real public clips.
QUERIES = [
    ("пассивный доход крипто гарантия заработок", 4),
    ("инвестиции 100 процентов доход в месяц", 4),
    ("онлайн казино занос промокод бонус", 4),
    ("крипто сигналы приватный канал профит", 4),
    ("разгон депозита ставки на спорт прогноз", 4),
    ("заработок в интернете без вложений схема", 4),
    ("криптовалюта удвоение депозита гарантия", 4),
    ("бинарные опционы стратегия 100% прибыль", 3),
    ("инвест клуб закрытый телеграм сигналы", 3),
    ("форекс робот автоматический заработок", 3),
    ("казино вулкан бонус за регистрацию промокод", 3),
    ("млм пирамида быстрые деньги реферал", 3),
    ("финансовая грамотность инвестиции для начинающих", 3),  # controls → expected LOW
    ("как защититься от финансовых мошенников", 2),
]

# Title-keyword → fact flags. Honest: the flag is grounded in the real title text.
_KW = {
    "promises_returns": ["доход", "процент", "%", "прибыл", "зараб", "100$", "1000$",
                         "x100", "х100", "умнож", "profit", "earn", "passive", "пассив"],
    "has_referral": ["реферал", "пригласи", "бонус за друга", "referral", "invite", "промокод"],
    "gambling_content": ["казино", "ставк", "слот", "casino", "bet", "рулетк", "покер",
                         "jackpot", "джекпот", "занос"],
    "aggressive_investment": ["срочно", "успей", "гаранти", "300%", "100%", "сегодня",
                              "guarantee", "urgent", "быстро"],
    "hidden_engagement": ["личк", "директ", "закрыт", "приватн", "подпис", "telegram",
                          "t.me", "канал", "dm"],
}


def facts_from_title(title: str) -> dict:
    t = title.lower()
    f = {k: any(kw in t for kw in kws) for k, kws in _KW.items()}
    f["has_license"] = False
    return f


def fetch(query: str, n: int) -> list[dict]:
    """Real public-metadata search via yt-dlp (no download, no AI)."""
    out = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--no-warnings", "--ignore-errors",
         "--print", "%(id)s\t%(title)s\t%(channel)s\t%(view_count)s",
         f"ytsearch{n}:{query}"],
        capture_output=True, text=True, timeout=90,
    ).stdout.strip()
    clips = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        vid, title = parts[0], parts[1]
        channel = parts[2] if len(parts) > 2 and parts[2] != "NA" else "youtube"
        try:
            views = int(parts[3]) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
        except ValueError:
            views = 0
        clips.append({"id": vid, "title": title, "channel": channel, "views": views})
    return clips


def seed(session) -> dict:
    from app.db.models import Content
    from app.db.risk_repo import upsert_content_risk
    from app.services.content_scoring import score_content

    seen: set[str] = set()
    rows = 0
    summary = []
    for query, n in QUERIES:
        for c in fetch(query, n):
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            cid = f"{ID_PREFIX}{c['id']}"
            url = f"https://www.youtube.com/watch?v={c['id']}"
            facts = facts_from_title(c["title"])
            a = score_content(facts, scheme_matches=0, related_objects=0, evidence_ids=[cid])

            row = session.get(Content, cid)
            if row is None:
                row = Content(id=cid, external_id=c["id"],
                              sha256=hashlib.sha256(url.encode()).hexdigest())
                session.add(row)
            row.source = "youtube"
            row.author = c["channel"]
            row.url = url
            row.lang = "ru"
            row.transcript = c["title"]          # feed caption = real title
            row.promises_returns = facts["promises_returns"]
            row.has_referral = facts["has_referral"]
            row.gambling_content = facts["gambling_content"]
            row.has_license = False
            session.commit()

            upsert_content_risk(session, cid, a.score, a.threat_level.value, a.breakdown,
                                a.recommendation, author=c["channel"], source="youtube",
                                url=url, reach={"views": c["views"]})
            rows += 1
            summary.append(f"  {a.score:>3} {a.threat_level.value:<8} {c['title'][:54]}")
    return {"seeded": rows, "summary": summary}


def clear(session) -> dict:
    from app.db.models import Content, ContentRisk
    n = 0
    for r in session.query(ContentRisk).filter(ContentRisk.content_id.like(f"{ID_PREFIX}%")).all():
        session.delete(r); n += 1
    for c in session.query(Content).filter(Content.id.like(f"{ID_PREFIX}%")).all():
        session.delete(c)
    session.commit()
    return {"cleared": n}


def main() -> None:
    from app.db.session import get_session

    gen = get_session()
    session = next(gen)
    try:
        if "--clear" in sys.argv:
            print("CLEARED:", clear(session))
            return
        res = seed(session)
        print(f"SEEDED {res['seeded']} real YouTube clips:")
        print("\n".join(res["summary"]))
    finally:
        session.close()


if __name__ == "__main__":
    main()
