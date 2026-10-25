"""Mock AI provider — fully offline, deterministic, NO external API calls.

Selected via AI_PROVIDER=mock (env or the Settings UI). Lets the whole pipeline
(claims extraction, narrative, embeddings, transcription, vision, OCR) run for a
demo without OpenAI — no network, no cost, no rate limits, reproducible output.

The fact extraction is keyword-driven on the input text, so the risk score still
*reflects* the content (a casino/invest caption scores high, a clean one low) —
it's a believable stand-in, not random noise.
"""
from __future__ import annotations

import hashlib
import json

from app.core.config import settings

# Keyword cues -> the 6 content facts. Deterministic, language-aware (ru/en).
_CUES = {
    "promises_returns": ("доход", "процент", "прибыл", "заработ", "%", "x100", "профит", "profit", "доллар"),
    "has_referral": ("реферал", "пригласи", "invite", "бонус за", "по промокоду", "промокод", "referral"),
    "has_license": ("лиценз", "регулятор", "license", "официальн"),
    "gambling_content": ("казино", "ставк", "слот", "casino", "bet", "букмек", "1xbet", "рулетк", "джекпот"),
    "aggressive_investment": ("срочно", "успей", "сейчас", "последний шанс", "не упусти", "только сегодня", "лимит"),
    "hidden_engagement": ("в лс", "личк", "закрыт", "секрет", "напиши", "t.me", "@", "подпис", "бот"),
}


# Offline semantic assist: paraphrased signs the lexicon may miss. Each hit quotes the
# text verbatim (a few words around the cue), so it passes the detector's quote check.
_SEMANTIC_CUES = (
    (r"капает|капают", "pyramid.unrealistic_return"),
    (r"вдвое|в два раза|в три раза|втрое", "pyramid.unrealistic_return"),
    (r"ничего делать не надо|без усилий|деньги работают", "pyramid.unrealistic_return"),
    (r"скинул\w*|скиньте|кто скинет", "shared.personal_transfer"),
    (r"сигнал\w*", "casino.native_win"),
    (r"занос\w*|иксы|\bx\d{2,}", "casino.native_win"),
    (r"крутим|рандом\w*", "lottery.random_draw"),
    (r"мест\w* (?:мало|осталось)|последн\w* (?:набор|день)", "pyramid.urgency"),
)


def _semantic_hits(user: str) -> list[dict]:
    import re

    text = user.split("Текст:", 1)[-1].strip()
    out, seen = [], set()
    for pattern, signal in _SEMANTIC_CUES:
        m = re.search(pattern, text, re.I)
        if not m or signal in seen:
            continue
        words = text[max(0, m.start() - 30):m.end() + 30].split()
        quote = " ".join(words[1:-1] if len(words) > 3 else words)
        if quote:
            out.append({"signal": signal, "quote": quote})
            seen.add(signal)
    return out


def _narrative(user: str) -> str:
    """A short report strictly from the provided facts (no invented numbers)."""
    try:
        facts = json.loads(user.split("Факты:", 1)[1].strip())
    except (ValueError, IndexError):
        return "Отчёт сформирован по фактам из разбивки признаков."
    found = [f for f in facts.get("findings", []) if f][:3]
    net = facts.get("network", {}) or {}
    parts = [f"Объект {facts.get('target', '')}: балл {facts.get('risk_score')}/100 ({facts.get('threat_level')})."]
    if found:
        parts.append("Основные признаки: " + "; ".join(found) + ".")
    parts.append(f"Связей в сети: {net.get('related_objects', 0)}, совпадений со схемами: "
                 f"{facts.get('scheme_matches', 0)}.")
    if facts.get("recommendation"):
        parts.append(f"Рекомендация: {facts['recommendation']}")
    return " ".join(parts)


class MockProvider:
    """Implements every AI interface (ChatLLM/Embedder/Transcriber/Vision/OCR/biometrics)."""

    # --- ChatLLM ---
    def complete(self, system: str, user: str) -> str:
        s = (system or "").lower()
        if "дословную" in s:                  # SafeNet semantic assist: [{signal, quote}]
            return json.dumps(_semantic_hits(user or ""), ensure_ascii=False)
        if "json" in s:                       # claims / content-facts extraction
            text = (user or "").lower()
            flags = {k: any(c in text for c in cues) for k, cues in _CUES.items()}
            return json.dumps(flags, ensure_ascii=False)
        if "Факты:" in (user or ""):          # investigation narrative, strictly from the facts
            return _narrative(user)
        return ("Признаки и балл рассчитаны детерминированным движком; подробности — в разбивке "
                "по признакам и в аналитической справке.")

    # --- Embedder ---
    def embed_text(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        dim = settings.dim_text
        seed = hashlib.sha256((text or "").encode("utf-8")).digest()
        # deterministic pseudo-vector in [0,1) from the hash (repeating the digest)
        return [seed[i % len(seed)] / 255.0 for i in range(dim)]

    # --- Transcriber ---
    def transcribe(self, audio: bytes, *, filename: str = "audio.mp3") -> str:
        return ("так пацаны заходим крутим lucky jet ставка пятьдесят тысяч ну давай давай занос "
                "ссылка в описании промокод AZAMAT регистрируйтесь по ссылке")

    # --- VisionTagger ---
    def tag(self, image: bytes, *, prompt: str | None = None) -> list[str]:
        return ["casino", "money", "chart"]

    # --- OCREngine ---
    def ocr(self, image: bytes) -> str:
        return "ГАРАНТИЯ ДОХОДА 300% • t.me/invest_vip"

    # --- Biometrics (deterministic small vectors) ---
    def embed_face(self, image: bytes) -> list[float] | None:
        return None

    def embed_voice(self, audio: bytes) -> list[float] | None:
        return None
