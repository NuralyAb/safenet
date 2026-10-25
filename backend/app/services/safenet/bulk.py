"""Bulk check — score thousands of posts at once (scalability, live on stage).

Input: CSV (column `text`, optional `author`, `source`, `url`, `views`), JSONL (field
`text` …) or plain text (one post per line). Rules + learned layer only — no LLM, no
network — so a laptop core does hundreds of posts per second. Flagged posts (score ≥ 40)
go to the review queue; the rest are only counted.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import time
from collections import Counter

from app.services.safenet import analyze_segments
from app.services.safenet.scoring import FLAG_THRESHOLD

MAX_ROWS = 50_000


def parse_rows(raw: bytes, filename: str = "") -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    name = filename.lower()
    rows: list[dict] = []
    if name.endswith(".jsonl") or (not name.endswith((".csv", ".txt")) and text.lstrip().startswith("{")):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and str(obj.get("text", "")).strip():
                rows.append(obj)
    elif name.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        for obj in reader:
            obj = {(k or "").strip().lower(): v for k, v in obj.items()}
            if (obj.get("text") or "").strip():
                rows.append(obj)
    else:
        rows = [{"text": line} for line in text.splitlines() if line.strip()]
    return rows[:MAX_ROWS]


def demo_rows(n: int = 5000, seed: int = 7) -> list[dict]:
    """A synthetic «feed»: ~6% schemes among ordinary posts (base rate closer to reality)."""
    from app.services.safenet.evaluation import load

    rng = random.Random(seed)
    pool = [r for name in ("dev", "test", "holdout") for r in load(name)]
    pos = [r for r in pool if r["label"] == 1]
    neg = [r for r in pool if r["label"] == 0]
    cities = ["Шымкент", "Алматы", "Астана", "Тараз", "Актобе", "Караганда"]
    out = []
    for i in range(n):
        src = rng.choice(pos) if rng.random() < 0.06 else rng.choice(neg)
        text = src["text"] + rng.choice(["", " 🙂", f" #{rng.choice(cities)}", " 🔥", " !!"])
        out.append({"text": text, "author": f"acc_{rng.randrange(1, 1500):04d}",
                    "source": rng.choice(["instagram", "tiktok", "telegram", "whatsapp"]),
                    "views": rng.randrange(50, 300_000)})
    return out


def run_bulk(rows: list[dict], *, session=None, persist: bool = True, label: str = "bulk") -> dict:
    t0 = time.perf_counter()
    results = []
    tracks: Counter = Counter()
    levels: Counter = Counter()
    langs: Counter = Counter()
    for i, row in enumerate(rows):
        text = str(row.get("text", ""))
        a, det = analyze_segments([("text", text)])
        levels[a.threat_level.value] += 1
        langs[det.language] += 1
        if a.score >= FLAG_THRESHOLD:
            tracks[a.track] += 1
        results.append((i, row, a))
    elapsed = time.perf_counter() - t0

    flagged = [(i, row, a) for i, row, a in results if a.score >= FLAG_THRESHOLD]
    persisted = 0
    if persist and session is not None and flagged:
        persisted = _persist(session, flagged, label)
    top = sorted(flagged, key=lambda x: -x[2].score)[:25]
    return {
        "rows": len(rows), "flagged": len(flagged), "persisted": persisted,
        "seconds": round(elapsed, 2), "items_per_second": round(len(rows) / elapsed, 1) if elapsed else None,
        "by_level": dict(levels), "by_track": dict(tracks), "languages": dict(langs),
        "top": [{"row": i + 1, "author": row.get("author") or "", "score": a.score,
                 "threat_level": a.threat_level.value, "track": a.track, "text": str(row.get("text", ""))[:200],
                 "signals": [b.get("label") or b["factor"] for b in a.breakdown if b.get("kind") == "signal"][:5]}
                for i, row, a in top],
    }


def _persist(session, flagged, label: str) -> int:
    from app.db.models import Content, ContentRisk
    from app.services.content_scoring import normalize_reach, priority_from

    n = 0
    seen: set[str] = set()
    for i, row, a in flagged:
        text = str(row.get("text", ""))
        author = (str(row.get("author") or "") or f"{label}#{i + 1}")[:250]
        cid = hashlib.sha256(f"{author}|{text}".encode("utf-8")).hexdigest()
        if cid in seen:
            continue
        seen.add(cid)
        reach = normalize_reach({"views": row.get("views") or 0})
        source = str(row.get("source") or "bulk")[:32]
        url = str(row.get("url") or "")
        risk = session.query(ContentRisk).filter_by(content_id=cid).one_or_none()
        if risk is None:
            session.add(ContentRisk(content_id=cid, author=author, source=source, url=url, score=a.score,
                                    threat_level=a.threat_level.value, breakdown=a.breakdown,
                                    recommendation=a.recommendation, track=a.track, lang=a.language,
                                    priority=priority_from(a.score, reach["views"]), **reach))
        if session.get(Content, cid) is None:
            session.add(Content(id=cid, external_id=cid, sha256=cid, source=source, author=author, url=url,
                                lang=a.language or "ru", caption=text))
        n += 1
    session.commit()
    return n
