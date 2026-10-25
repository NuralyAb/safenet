"""Signal detection: text segments -> explainable hits with verbatim quotes.

A content item is a list of SEGMENTS (caption, speech transcript, on-screen OCR,
chat messages…). Every lexicon signal runs on every normalised view of every
segment; each hit keeps the quote, where it came from (source) and whether it was
hidden by obfuscation (view != base). The LLM can add semantic hits, but only with
a quote that literally occurs in the text — a hallucinated quote is dropped.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from app.services.safenet import lexicon, numeric
from app.services.safenet.normalize import build_views, detect_language, fold

SOURCE_LABELS = {
    "text": "текст поста", "caption": "подпись", "transcript": "речь (транскрипт)",
    "ocr": "текст на изображении", "stream": "транскрипт эфира", "chat": "сообщение чата",
    "llm": "семантический анализ (LLM)", "vision": "визуальные теги", "group": "анализ группы",
    "model": "модель по размеченным примерам",
}
VIEW_LABELS = {
    "base": "", "deobf": "скрыто подменой символов", "collapsed": "скрыто разрядкой букв",
    "translit": "написано транслитом", "emoji": "закодировано эмодзи",
    "numwords": "числа прописью",
}
MAX_QUOTES = 3


@dataclass
class Quote:
    text: str
    source: str = "text"
    view: str = "base"


@dataclass
class Hit:
    signal: str
    track: str
    strength: float
    quotes: list[Quote] = field(default_factory=list)
    note: str = ""

    @property
    def label(self) -> str:
        return lexicon.label_for(self.signal)

    @property
    def sources(self) -> list[str]:
        return sorted({q.source for q in self.quotes})

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label
        return d


@dataclass
class Detection:
    hits: dict[str, Hit]
    language: str
    identifiers: dict
    text: str

    def has(self, signal: str) -> bool:
        return signal in self.hits

    def strength(self, signal: str) -> float:
        h = self.hits.get(signal)
        return h.strength if h else 0.0

    def to_dict(self) -> dict:
        return {"hits": [h.to_dict() for h in self.hits.values()], "language": self.language,
                "identifiers": self.identifiers}

    @classmethod
    def from_dict(cls, data: dict) -> "Detection":
        """Rebuild a serialised detection (Celery hands it between pipeline stages)."""
        hits = {}
        for h in data.get("hits", []):
            hits[h["signal"]] = Hit(h["signal"], h.get("track", ""), float(h.get("strength", 0)),
                                    [Quote(**q) for q in h.get("quotes", [])], h.get("note", ""))
        return cls(hits=hits, language=data.get("language", ""),
                   identifiers=data.get("identifiers", {}), text="")


def _quote(views, view_name: str, view_text: str, start: int, end: int) -> str:
    """Cut a readable quote: from the original text when offsets are shared."""
    src = views.original if (views.aligned and view_name in ("base", "deobf")) else view_text
    s = max(0, start)
    e = min(len(src), end)
    # extend to word boundaries for readability, cap length
    while s > 0 and src[s - 1].isalnum() and start - s < 15:
        s -= 1
    while e < len(src) and src[e].isalnum() and e - end < 15:
        e += 1
    q = re.sub(r"\s+", " ", src[s:e]).strip()
    return q if len(q) <= 90 else q[:87] + "…"


def _excluded(sig: lexicon.SignalDef, text: str, start: int, end: int) -> bool:
    if not sig.compiled_exclude:
        return False
    window = text[max(0, start - 40):min(len(text), end + 40)]
    return any(rx.search(window) for rx in sig.compiled_exclude)


def _add(hits: dict[str, Hit], signal: str, track: str, strength: float, quote: Quote | None,
         note: str = "") -> None:
    h = hits.get(signal)
    stronger = False
    if h is None:
        h = hits[signal] = Hit(signal=signal, track=track, strength=strength, note=note)
    else:
        if strength > h.strength:
            h.strength = strength
            stronger = True
            if note:
                h.note = note
        elif note and not h.note:
            h.note = note
    # the same phrase seen through another view («Қатысу ақылы» / «катысу акылы») is one quote
    if quote and quote.text and all(_squash(q.text) != _squash(quote.text) for q in h.quotes):
        if stronger:                      # the quote that justifies the strength goes first
            h.quotes = [quote] + h.quotes[:MAX_QUOTES - 1]
        elif len(h.quotes) < MAX_QUOTES:
            h.quotes.append(quote)


def _scan_segment(hits: dict[str, Hit], text: str, source: str) -> None:
    views = build_views(text)
    view_items = views.items()
    for sig in lexicon.SIGNALS:
        for groups, strength in ((sig.compiled, 1.0), (sig.compiled_weak, 0.5)):
            if not groups or (strength < 1.0 and sig.id in hits and hits[sig.id].strength >= 1.0):
                continue
            seen_spans: set[tuple[int, int]] = set()
            for view_name, view_text in view_items:
                for rx in groups:
                    for m in rx.finditer(view_text):
                        if _excluded(sig, view_text, m.start(), m.end()):
                            continue
                        # same span on an aligned view = same quote, keep the plainest view
                        aligned_view = views.aligned and view_name in ("base", "deobf")
                        if aligned_view and (m.start(), m.end()) in seen_spans:
                            break
                        if aligned_view:
                            seen_spans.add((m.start(), m.end()))
                        _add(hits, sig.id, sig.track, strength,
                             Quote(_quote(views, view_name, view_text, m.start(), m.end()),
                                   source, view_name))
                        break
    # numeric extractors: de-obfuscated view (offsets shared with original) + translit
    num_views = [("deobf", views.deobf)]
    if views.collapsed != views.deobf:
        num_views.append(("collapsed", views.collapsed))         # «Д О Х О Д 300% за месяц»
    if views.translit:
        num_views.append(("translit", views.translit))
    if views.numwords:
        num_views.append(("numwords", views.numwords))       # «вложил двадцать тысяч»
    if views.emoji:
        num_views.append(("emoji", views.emoji))
    for view_name, num_text in num_views:
        found = numeric.return_ratio(num_text) + numeric.return_rate(num_text) + numeric.multipliers(num_text)
        for nh in found:
            s, e = nh.span
            _add(hits, "pyramid.unrealistic_return", "pyramid", nh.strength,
                 Quote(_quote(views, view_name, num_text, s, e), source,
                       "base" if view_name == "deobf" else view_name), note=nh.note)
        if found:
            break
    num_text = views.deobf
    for digits, (s, e) in numeric.card_numbers(num_text):
        _add(hits, "shared.personal_transfer", "shared", 1.0,
             Quote(numeric.mask_card(digits), source, "base"),
             note="в тексте номер банковской карты")


def _identifiers(text: str) -> dict:
    from app.services.extract import extract_identifiers

    ids = extract_identifiers(text)
    folded = fold(text)
    ids["cards"] = [numeric.mask_card(d) for d, _ in numeric.card_numbers(folded)]
    # promo code = a latin/digit token with at least one letter right after «промокод»
    ids["promo_codes"] = sorted({m.group(1).upper() for m in re.finditer(
        r"(?:промо\s?код\w*|promo\s?(?:code|kod)\w*|\bpromik\w*|\bпромик\w*|\bпромо\b|\bpromo\b|по коду|\bкод|\bkod)"
        r"\s?[:\-–—«\"']?\s?([a-z0-9_]*[a-z][a-z0-9_]*)\b",
        folded) if 3 <= len(m.group(1)) <= 20})
    ids["short_links"] = sorted({m.group(0) for m in re.finditer(
        r"(?:https?://)?(?:" + lexicon._SHORTENERS + r")/[\w\-]+", folded)})
    ids["whatsapp"] = sorted({m.group(0) for m in re.finditer(
        r"(?:chat\.whatsapp\.com/[\w]+|wa\.me/\+?\d+)", folded)})
    return ids


# --- LLM semantic extraction (optional, hallucination-guarded) ---------------
_LLM_SIGNALS = (
    "lottery.paid_entry", "lottery.random_draw", "lottery.organizer_income", "lottery.free_mechanics",
    "casino.gambling", "casino.native_win", "casino.promo_code", "casino.tracking_link",
    "pyramid.unrealistic_return", "pyramid.urgency", "pyramid.referral", "pyramid.payout_proofs",
    "pyramid.structure_roles", "shared.personal_transfer", "shared.warning_context",
)
_LLM_SYSTEM = (
    "Ты помогаешь модератору находить ПРИЗНАКИ возможных нарушений в соцсетях Казахстана "
    "(русский, казахский, смесь, транслит, сленг). Ты НЕ выносишь вердикт и НЕ ставишь балл. "
    "Найди в тексте признаки из списка и для каждого приведи ДОСЛОВНУЮ короткую цитату из текста "
    "(3–12 слов, без изменений). Если признака нет — не включай его. Верни СТРОГО JSON-массив "
    "объектов {\"signal\": <id>, \"quote\": <цитата>} без пояснений.\nСписок признаков:\n"
    + "\n".join(f"{sid} — {lexicon.label_for(sid)}" for sid in _LLM_SIGNALS)
)


def llm_prompt(text: str) -> tuple[str, str]:
    return _LLM_SYSTEM, f"Текст:\n{text[:6000]}"


def _squash(s: str) -> str:
    return re.sub(r"[^\w%]+", " ", fold(s)).strip()


def parse_llm_hits(raw: str, text: str) -> list[tuple[str, str]]:
    """Parse [{signal, quote}] and keep only quotes that really occur in `text`."""
    if not raw:
        return []
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    haystack = _squash(text)
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        sid, quote = str(item.get("signal", "")), str(item.get("quote", "")).strip()
        if sid not in _LLM_SIGNALS or len(quote) < 3:
            continue
        if _squash(quote) and _squash(quote) in haystack:      # anti-hallucination guard
            out.append((sid, quote[:90]))
    return out


def detect(segments: list[tuple[str, str]], *, llm=None, vision_tags: list[str] | None = None,
           use_model: bool = True) -> Detection:
    """Run the full detector over (source, text) segments.

    `use_model` adds the learned «похоже на размеченные схемы» signal (model.py)."""
    hits: dict[str, Hit] = {}
    texts = []
    for source, text in segments:
        if text and text.strip():
            texts.append(text)
            _scan_segment(hits, text, source)
    full = "\n".join(texts)

    if llm is not None and full.strip():
        try:
            system, user = llm_prompt(full)
            for sid, quote in parse_llm_hits(llm.complete(system, user), full):
                sig = lexicon.BY_ID[sid]
                # semantic hits are slightly weaker than an exact lexical rule
                _add(hits, sid, sig.track, 0.8 if sid not in hits else hits[sid].strength,
                     Quote(quote, "llm", "base"))
        except Exception:  # noqa: BLE001 — the LLM is an assist; rules still work offline
            pass

    if vision_tags:
        from app.services.pipeline import gambling_from_tags
        if gambling_from_tags(vision_tags):
            _add(hits, "visual.gambling", "casino", 1.0,
                 Quote(", ".join(vision_tags[:5]), "vision", "base"),
                 note="на изображении — интерфейс казино/слотов")

    if use_model and full.strip():
        from app.services.safenet import model
        track, p, why = model.predict(full)
        if track != "none" and p >= model.MIN_P:
            hits["ml.similar"] = Hit("ml.similar", track, round(p, 3),
                                     [Quote(", ".join(why) or "—", "model", "base")],
                                     note=f"вероятность {p:.0%}, трек «{lexicon.TRACK_LABELS[track].lower()}»")

    return Detection(hits=hits, language=detect_language(full), identifiers=_identifiers(full), text=full)


def facts_to_hits(facts: dict) -> dict[str, Hit]:
    """Legacy boolean facts (old pipeline / LLM flags) -> weak hits, when no text is available."""
    mapping = {
        "gambling_content": ("casino.gambling", "casino", 0.8),
        "promises_returns": ("pyramid.unrealistic_return", "pyramid", 0.6),
        "has_referral": ("pyramid.referral", "pyramid", 0.8),
        "aggressive_investment": ("pyramid.urgency", "pyramid", 0.8),
        "hidden_engagement": ("pyramid.closed_chat", "pyramid", 0.8),
    }
    hits: dict[str, Hit] = {}
    for key, (sid, track, strength) in mapping.items():
        if facts.get(key):
            _add(hits, sid, track, strength, Quote("(флаг извлечения фактов)", "llm", "base"))
    return hits
