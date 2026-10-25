"""Campaigns — «аккаунты, каналы и домены как единая сеть».

A scheme is rarely one account: three «гив» pages collect money to ONE Kaspi number,
casino «блогеры» push the SAME promo code, curators copy the SAME text. This groups
every account / group in the review queue into networks via:

  * shared hard identifiers: phone, card (masked), promo code, short link, Telegram,
    WhatsApp link, domain, wallet
  * shared templates: the same (normalised) text posted by different accounts

and ranks the networks by risk × total reach, so an analyst opens the biggest scheme
first instead of 40 separate posts. Pure Postgres data (works without Neo4j).
"""
from __future__ import annotations

from collections import Counter, defaultdict

from app.services.content_scoring import priority_from
from app.services.safenet.detector import _identifiers
from app.services.safenet.group import _template_key

ID_KINDS = {"phones": "телефон", "cards": "карта", "promo_codes": "промокод", "short_links": "короткая ссылка",
            "telegram": "telegram", "whatsapp": "whatsapp", "domains": "домен", "wallets": "кошелёк"}
# identifiers too generic to prove a link on their own (social networks, big platforms)
_GENERIC = {"telegram:joinchat", "telegram:share"} | {f"domains:{d}" for d in (
    "t.me", "instagram.com", "kaspi.kz", "facebook.com", "fb.com", "linkedin.com", "youtube.com", "youtu.be",
    "tiktok.com", "vk.com", "google.com", "twitter.com", "x.com", "wa.me", "whatsapp.com", "telegram.org",
    "apple.com", "play.google.com", "gmail.com", "mail.ru", "yandex.ru", "egov.kz", "gov.kz")}


class _DSU:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _text(content) -> str:
    return "\n".join(x for x in (content.caption, content.transcript, content.ocr_text) if x) if content else ""


def build_campaigns(session, *, min_accounts: int = 2, limit: int = 50) -> list[dict]:
    from app.db.models import Content, ContentRisk

    risks = session.query(ContentRisk).all()
    if not risks:
        return []
    contents = {c.id: c for c in session.query(Content).filter(Content.id.in_([r.content_id for r in risks]))}

    by_author: dict[str, list] = defaultdict(list)
    ident_accounts: dict[str, set[str]] = defaultdict(set)
    template_accounts: dict[str, set[str]] = defaultdict(set)
    template_example: dict[str, str] = {}
    for r in risks:
        author = r.author or ""
        if not author or author == "(не указан)":
            continue
        c = contents.get(r.content_id)
        text = _text(c)
        by_author[author].append((r, c))
        if not text:
            continue
        ids = _identifiers(text)
        for kind in ID_KINDS:
            for v in ids.get(kind, []):
                key = f"{kind}:{str(v).lower()}"
                if key not in _GENERIC:
                    ident_accounts[key].add(author)
        tkey = " ".join(_template_key(text).split()[:14])
        if len(tkey.split()) >= 8:
            template_accounts[tkey].add(author)
            template_example.setdefault(tkey, text[:160])

    dsu = _DSU()
    links: dict[str, list[str]] = defaultdict(list)       # root-independent: identifier -> accounts
    for key, accs in list(ident_accounts.items()) + [(f"template:{k}", v) for k, v in template_accounts.items()]:
        if len(accs) < 2:
            continue
        accs = sorted(accs)
        for a in accs[1:]:
            dsu.union(accs[0], a)
        links[key] = accs

    components: dict[str, set[str]] = defaultdict(set)
    for key, accs in links.items():
        for a in accs:
            components[dsu.find(a)].add(a)

    out = []
    for root, accounts in components.items():
        if len(accounts) < min_accounts:
            continue
        rows = [(r, c) for a in accounts for r, c in by_author[a]]
        scores = [r.score for r, _ in rows]
        views = sum(r.views or 0 for r, _ in rows)
        tracks = Counter(r.track for r, _ in rows if r.track and r.score >= 40)
        shared = []
        for key, accs in links.items():
            if set(accs) <= accounts:
                kind, value = key.split(":", 1)
                if kind == "template":
                    shared.append({"kind": "шаблон текста", "value": template_example.get(value, value)[:120],
                                   "accounts": accs})
                else:
                    shared.append({"kind": ID_KINDS[kind], "value": value, "accounts": accs})
        shared.sort(key=lambda s: (-len(s["accounts"]), s["kind"]))
        times = [c.collected_at for _, c in rows if c is not None and c.collected_at]
        max_score = max(scores) if scores else 0
        top = sorted(rows, key=lambda x: -x[0].score)[:3]
        accounts_info = []
        for a in sorted(accounts):
            ar = by_author[a]
            accounts_info.append({"account": a, "source": ar[0][0].source if ar else "",
                                  "materials": len(ar), "max_score": max((r.score for r, _ in ar), default=0)})
        out.append({
            "id": root,
            "accounts": accounts_info,
            "materials": len(rows),
            "flagged": sum(1 for s in scores if s >= 40),
            "total_views": views,
            "max_score": max_score,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "track": tracks.most_common(1)[0][0] if tracks else "",
            "tracks": dict(tracks),
            "platforms": sorted({r.source for r, _ in rows if r.source}),
            "shared": shared[:12],
            "first_seen": min(times).isoformat() if times else None,
            "last_seen": max(times).isoformat() if times else None,
            "top_materials": [{"content_risk_id": r.id, "author": r.author, "score": r.score,
                               "threat_level": r.threat_level, "text": _text(c)[:180]} for r, c in top],
            "priority": priority_from(max_score, views),
        })
    out.sort(key=lambda c: (-c["priority"], -c["materials"]))
    return out[:limit]
