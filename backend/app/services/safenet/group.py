"""Group / chat analysis — track 3 «Структура группы» (and paid-lottery chats).

A single message rarely proves a scheme; the GROUP does: one organizer collecting
money, several «curators» repeating the same script, a flood of near-identical
«выплата пришла 🙏» reviews from different people. Input is a chat export:

  * Telegram Desktop export  (result.json: {"name", "messages": [{"from", "text", "date"}]})
  * WhatsApp «Экспорт чата»  (.txt: «12.10.2026, 14:03 - Имя: текст» / «[12.10.26, 14:03:11] Имя: текст»)
  * plain text, one message per line: «[Имя]: текст» or «Имя: текст»

Output: the group's risk (same deterministic scorer, plus group-level signals),
member roles, the most risky messages with quotes, template clusters.
Roles are CANDIDATES for an analyst, not accusations.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.services.safenet import detector
from app.services.safenet.detector import Hit, Quote
from app.services.safenet.normalize import fold
from app.services.safenet.scoring import FLAG_THRESHOLD, assessment_dict, score_detection

MAX_MESSAGES = 5000

# signals that make a message «money-related» (used for roles)
_MONEY_SIGNALS = {"pyramid.unrealistic_return", "pyramid.recruitment_income", "shared.personal_transfer",
                  "lottery.paid_entry", "lottery.organizer_income", "pyramid.entry_payment",
                  "casino.promo_code", "casino.tracking_link"}
_ROLE_WORDS = re.compile(r"куратор|наставник|ментор|админ|организатор|лидер|жетекши|кенесши|менеджер|"
                         r"помощник|модератор|ассистент|көмекші|комекши", re.I)


@dataclass
class Message:
    author: str
    text: str
    ts: str = ""


@dataclass
class ChatExport:
    name: str
    platform: str                    # telegram | whatsapp | text
    messages: list[Message] = field(default_factory=list)


# --- parsing ----------------------------------------------------------------
def _tg_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in value)
    return ""


_WA_LINE = re.compile(
    r"^\[?(?P<ts>\d{1,2}[./]\d{1,2}[./]\d{2,4},?\s\d{1,2}:\d{2}(?::\d{2})?)\]?\s?(?:-\s)?(?P<author>[^:]{1,60}):\s(?P<text>.*)$")
_PLAIN_LINE = re.compile(r"^\s*\[?(?P<author>[^\]:\n]{1,60})\]?\s?:\s(?P<text>.+)$")


def parse_chat(raw: str | bytes, filename: str = "") -> ChatExport:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    raw = raw.lstrip("﻿")
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            msgs = [Message(str(m.get("from") or m.get("actor") or "?"), _tg_text(m.get("text", "")), str(m.get("date", "")))
                    for m in data.get("messages", []) if m.get("type", "message") == "message"]
            return ChatExport(str(data.get("name") or filename or "Telegram-группа"), "telegram",
                              [m for m in msgs if m.text.strip()][:MAX_MESSAGES])
        except (json.JSONDecodeError, AttributeError):
            pass
    lines = raw.splitlines()
    wa = [m for m in (_WA_LINE.match(l) for l in lines) if m]
    if len(wa) >= max(2, len(lines) // 3):
        msgs: list[Message] = []
        for line in lines:
            m = _WA_LINE.match(line)
            if m:
                msgs.append(Message(m.group("author").strip(), m.group("text"), m.group("ts")))
            elif msgs and line.strip():                 # multi-line message continuation
                msgs[-1].text += "\n" + line
        msgs = [m for m in msgs if "<Без медиафайлов>" not in m.text and "<Media omitted>" not in m.text]
        return ChatExport(filename or "WhatsApp-группа", "whatsapp", msgs[:MAX_MESSAGES])
    msgs = []
    for line in lines:
        m = _PLAIN_LINE.match(line)
        if m:
            msgs.append(Message(m.group("author").strip(), m.group("text")))
        elif msgs and line.strip():
            msgs[-1].text += "\n" + line
        elif line.strip():
            msgs.append(Message("?", line))
    return ChatExport(filename or "Чат", "text", msgs[:MAX_MESSAGES])


# --- template detection -------------------------------------------------------
def _template_key(text: str) -> str:
    t = fold(text)
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^\w#]+", " ", t)
    return " ".join(t.split())


def _shingles(key: str, k: int = 3) -> set[str]:
    words = key.split()
    return {" ".join(words[i:i + k]) for i in range(max(1, len(words) - k + 1))}


def template_clusters(messages: list[Message], *, min_size: int = 3, min_authors: int = 2,
                      threshold: float = 0.7) -> list[dict]:
    """Near-duplicate messages (Jaccard of word 3-shingles) posted by different people."""
    items = [(i, _template_key(m.text)) for i, m in enumerate(messages)]
    items = [(i, k) for i, k in items if len(k.split()) >= 4]
    clusters: list[dict] = []
    for i, key in items:
        sh = _shingles(key)
        for c in clusters:
            inter = len(sh & c["shingles"])
            union = len(sh | c["shingles"]) or 1
            if inter / union >= threshold:
                c["members"].append(i)
                break
        else:
            clusters.append({"shingles": sh, "members": [i], "key": key})
    out = []
    for c in clusters:
        authors = {messages[i].author for i in c["members"]}
        if len(c["members"]) >= min_size and len(authors) >= min_authors:
            out.append({"size": len(c["members"]), "authors": sorted(authors),
                        "example": messages[c["members"][0]].text[:200]})
    return sorted(out, key=lambda c: c["size"], reverse=True)


# --- analysis ---------------------------------------------------------------
def analyze_chat(export: ChatExport, *, evidence_ids: list[str] | None = None) -> dict:
    msgs = export.messages
    per_msg = []
    merged: dict[str, Hit] = {}
    ids_all: dict[str, set] = defaultdict(set)
    author_stats: dict[str, Counter] = defaultdict(Counter)

    for idx, m in enumerate(msgs):
        det = detector.detect([("chat", m.text)])
        a = score_detection(det)
        author_stats[m.author]["messages"] += 1
        sig_ids = set(det.hits)
        if a.score >= FLAG_THRESHOLD:
            author_stats[m.author]["risky"] += 1
        author_stats[m.author]["money"] += len(sig_ids & _MONEY_SIGNALS)
        if "pyramid.payout_proofs" in sig_ids:
            author_stats[m.author]["proofs"] += 1
        if _ROLE_WORDS.search(m.author) or "pyramid.structure_roles" in sig_ids:
            author_stats[m.author]["role_word"] += 1
        for sid, h in det.hits.items():
            tgt = merged.get(sid)
            if tgt is None:
                tgt = merged[sid] = Hit(sid, h.track, h.strength, note=h.note)
            stronger = h.strength > tgt.strength
            tgt.strength = max(tgt.strength, h.strength)
            if stronger and h.note:
                tgt.note = h.note
            for q in h.quotes:
                quote = Quote(f"{m.author}: {q.text}", "chat", q.view)
                if stronger:
                    tgt.quotes = [quote] + tgt.quotes[:detector.MAX_QUOTES - 1]
                    stronger = False
                elif len(tgt.quotes) < detector.MAX_QUOTES:
                    tgt.quotes.append(quote)
        for k, v in det.identifiers.items():
            ids_all[k].update(v)
        per_msg.append({"index": idx, "author": m.author, "ts": m.ts, "text": m.text[:400],
                        "score": a.score, "level": a.threat_level.value, "track": a.track,
                        "signals": [h.label for h in det.hits.values() if h.signal != "shared.warning_context"]})

    # group-level signals
    templates = template_clusters(msgs)
    if templates:
        t = templates[0]
        merged["group.template_messages"] = Hit(
            "group.template_messages", "pyramid", 1.0,
            [Quote(f"{t['size']} похожих сообщений от {len(t['authors'])} участников: «{t['example'][:80]}»", "group")],
            note=f"{len(templates)} кластер(ов) шаблонных сообщений")
    proof_authors = [a for a, s in author_stats.items() if s["proofs"]]
    if len(proof_authors) >= 3:
        merged["group.proof_flood"] = Hit(
            "group.proof_flood", "pyramid", 1.0,
            [Quote(f"отзывы о выплатах от {len(proof_authors)} участников: " + ", ".join(proof_authors[:5]), "group")],
            note="массовые «подтверждения выплат»")

    ranked = sorted(author_stats.items(), key=lambda kv: (kv[1]["money"], kv[1]["risky"], kv[1]["messages"]),
                    reverse=True)
    organizer = ranked[0][0] if ranked and ranked[0][1]["money"] > 0 else ""
    curators = [a for a, s in ranked[1:]
                if (s["role_word"] and (s["money"] or s["risky"])) or s["money"] >= 2][:10]
    if organizer and curators:
        merged["group.organizer_curators"] = Hit(
            "group.organizer_curators", "pyramid", 1.0,
            [Quote(f"организатор: {organizer}; кураторы: {', '.join(curators[:5])}", "group")],
            note=f"организатор и {len(curators)} куратор(ов)")

    identifiers = {k: sorted(v) for k, v in ids_all.items()}
    a_dict = assessment_dict(score_detection(hits=merged, identifiers=identifiers, evidence_ids=evidence_ids))

    members = []
    for author, s in ranked:
        role = "организатор (кандидат)" if author == organizer else (
            "куратор (кандидат)" if author in curators else "участник")
        members.append({"author": author, "messages": s["messages"], "risky_messages": s["risky"],
                        "money_signals": s["money"], "payout_reviews": s["proofs"], "role": role})

    langs = Counter(detector.detect_language(m.text) for m in msgs[:300])
    return {
        "group": export.name, "platform": export.platform, "messages": len(msgs),
        "authors": len(author_stats),
        "risk": a_dict,
        "members": members[:50],
        "top_messages": sorted(per_msg, key=lambda x: x["score"], reverse=True)[:12],
        "flagged_messages": sum(1 for p in per_msg if p["score"] >= FLAG_THRESHOLD),
        "templates": templates[:5],
        "identifiers": {k: v[:30] for k, v in identifiers.items()},
        "languages": dict(langs.most_common()),
        "organizer": organizer, "curators": curators,
    }
