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


class MockProvider:
    """Implements every AI interface (ChatLLM/Embedder/Transcriber/Vision/OCR/biometrics)."""

    # --- ChatLLM ---
    def complete(self, system: str, user: str) -> str:
        s = (system or "").lower()
        if "json" in s:                       # claims / content-facts extraction
            text = (user or "").lower()
            flags = {k: any(c in text for c in cues) for k, cues in _CUES.items()}
            return json.dumps(flags, ensure_ascii=False)
        # narrative / report
        return ("Демо-режим (mock): признаки извлечены детерминированным движком без "
                "обращения к внешним API. Балл рассчитан risk-движком по фактам.")

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
        return ("вложи и получай гарантированный доход, подпишись на телеграм-канал, "
                "переходи по ссылке (демо-транскрипт mock-режима)")

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
