"""Adaptation — «схемы быстро меняют форму».

1. Emerging wording: words that are frequent in FLAGGED materials (from different
   accounts) but rare in clean ones and NOT covered by any lexicon pattern — new brand
   names, new slang, new crash games. Candidates for an analyst to add to the lexicon.
2. Live quality from analyst decisions: per signal, how often a material it fired on
   was confirmed («передать специалисту» / «наблюдать») vs dismissed as a false
   positive — shows which sign needs tuning, from real work rather than test sets.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

from app.services.safenet import lexicon
from app.services.safenet.normalize import build_views

_WORD = re.compile(r"[a-zа-я][a-zа-я0-9]{3,}")
_STOP = set("""
этот этого этой всех всем только будет было были есть очень можно нужно когда тогда потом себя тебя меня
наши наших ваши ваших свой свою своих если чтобы через после перед между более менее также который которые
сегодня завтра вчера здесь всего каждый каждую каждого просто вообще теперь давно спасибо друзья ребята
девочки пожалуйста привет всего пишите напишите тысяч тенге мын тенге барлык барлыгы осы бул мен сен биз
сиз оларды ушин жане емес болады болып кейин дейин бугин ертен кешке тагы кана
выше ниже больше меньше лучшие лучший лучше вопросы вопрос день дней неделю месяц год года года
человек людей время раза разом многие много мало тоже какой какая какие такой такая такие просто
""".split())
_STRIP = re.compile(r"(?:https?://\S+|www\.\S+|\S+\.(?:com|net|ru|kz|io|me|xyz|top|site|app|bet)\S*|@\w+|t\.me/\S+)")


def _words(text: str) -> set[str]:
    """Words of the material as written (folded + translit), minus links, @handles, digits."""
    from app.services.safenet.normalize import _translit
    v = build_views(_STRIP.sub(" ", text))
    joined = " ".join(x for x in (v.base, _translit(v.base)) if x)     # no leet fixing: «777» stays digits
    return {w for w in _WORD.findall(joined) if w not in _STOP and not any(ch.isdigit() for ch in w)}


def _quoted_words(breakdown) -> set[str]:
    """Words already used as evidence by the signals that fired on this material."""
    out: set[str] = set()
    for b in breakdown or []:
        for q in b.get("quotes", []) or []:
            out |= _words(q.get("text", ""))
    return out


@lru_cache(maxsize=20000)
def _covered(word: str) -> bool:
    for sig in lexicon.SIGNALS:
        for rx in sig.compiled + sig.compiled_weak:
            if rx.search(word):
                return True
    return False


def emerging_terms(session, *, top: int = 30, min_docs: int = 2) -> dict:
    from app.db.models import Content, ContentRisk

    risks = session.query(ContentRisk).all()
    contents = {c.id: c for c in session.query(Content).filter(Content.id.in_([r.content_id for r in risks]))} \
        if risks else {}
    flag_df: Counter = Counter()
    quoted_df: Counter = Counter()
    clean_df: Counter = Counter()
    authors: dict[str, set] = defaultdict(set)
    tracks: dict[str, Counter] = defaultdict(Counter)
    example: dict[str, str] = {}
    n_flag = n_clean = 0
    for r in risks:
        c = contents.get(r.content_id)
        text = "\n".join(x for x in ((c.caption, c.transcript, c.ocr_text) if c else ()) if x)
        if not text:
            continue
        words = _words(text)
        if r.score >= 40:
            n_flag += 1
            quoted = _quoted_words(r.breakdown)
            for w in words:
                flag_df[w] += 1
                if w in quoted:
                    quoted_df[w] += 1
                authors[w].add(r.author)
                if r.track:
                    tracks[w][r.track] += 1
                example.setdefault(w, text[:160])
        else:
            n_clean += 1
            clean_df.update(words)
    # background of known-clean language (labelled negatives) so everyday words drop out
    from app.services.safenet.evaluation import load
    for name in ("dev", "test", "holdout"):
        for row in load(name):
            if row["label"] == 0:
                n_clean += 1
                clean_df.update(_words(row["text"]))

    out = []
    for w, f in flag_df.items():
        # covered = the lexicon already uses this word as evidence in most of its materials
        if f < min_docs or len(authors[w]) < 2 or _covered(w) or quoted_df[w] * 2 >= f:
            continue
        p_flag = (f + 0.5) / (n_flag + 1)
        p_clean = (clean_df[w] + 0.5) / (n_clean + 1)
        lift = math.log(p_flag / p_clean)
        if lift <= math.log(3):
            continue
        out.append({"term": w, "flagged_materials": f, "clean_materials": clean_df[w],
                    "accounts": len(authors[w]), "lift": round(lift, 2),
                    "track": tracks[w].most_common(1)[0][0] if tracks[w] else "",
                    "example": example.get(w, "")})
    out.sort(key=lambda x: (-x["lift"] * math.log1p(x["flagged_materials"]), x["term"]))
    return {"flagged_materials": n_flag, "clean_materials": n_clean, "terms": out[:top]}


def feedback_quality(session) -> dict:
    from app.db.models import ContentRisk

    rows = session.query(ContentRisk).filter(ContentRisk.disposition.in_(("escalated", "watching", "dismissed"))).all()
    per: dict[str, Counter] = defaultdict(Counter)
    total = Counter()
    for r in rows:
        verdict = "dismissed" if r.disposition == "dismissed" else "confirmed"
        total[verdict] += 1
        for b in r.breakdown or []:
            if b.get("kind", "signal") == "signal" and (b.get("contribution") or 0) > 0:
                per[b.get("factor", "")][verdict] += 1
    signals = []
    for sid, c in per.items():
        n = c["confirmed"] + c["dismissed"]
        signals.append({"signal": sid, "label": lexicon.label_for(sid), "decisions": n,
                        "confirmed": c["confirmed"], "dismissed": c["dismissed"],
                        "precision": round(c["confirmed"] / n, 3) if n else None})
    signals.sort(key=lambda s: (-(s["dismissed"]), s["precision"] or 0))
    n = total["confirmed"] + total["dismissed"]
    return {"decisions": n, "confirmed": total["confirmed"], "dismissed": total["dismissed"],
            "precision": round(total["confirmed"] / n, 3) if n else None, "signals": signals}
