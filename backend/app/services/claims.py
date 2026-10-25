"""NLP claim extraction — turn post text into the boolean risk factors.

The LLM extracts FACTS (does the text promise returns? referral? license?
gambling?). It returns strict JSON; we parse defensively. These flags feed the
deterministic Risk Engine — the LLM still never assigns the score.
"""
from __future__ import annotations

import json

CLAIM_KEYS = ("promises_returns", "has_referral", "has_license", "gambling_content")
# Intensifier signals — they don't add new ТЗ risk factors (the 6 weights stay
# fixed); they grade the STRENGTH of the parent factor in per-video scoring.
SIGNAL_KEYS = ("aggressive_investment", "hidden_engagement")
CONTENT_FACT_KEYS = CLAIM_KEYS + SIGNAL_KEYS

_SYSTEM = (
    "Ты извлекаешь признаки финансового мошенничества из текста поста. "
    "Верни СТРОГО JSON с булевыми полями (true/false), без пояснений:\n"
    "promises_returns — обещание прибыли / высокой или гарантированной доходности;\n"
    "has_referral — реферальная схема, «пригласи друзей», бонус за приглашение;\n"
    "has_license — упоминание лицензии / регулятора / легальности;\n"
    "gambling_content — казино, ставки, слоты, букмекер."
)

# Richer extraction for per-video scoring: the 4 claim flags + 2 intensifiers
# that map to the ТЗ patterns «агрессивные инвестиционные призывы» и «скрытые
# способы вовлечения аудитории».
_CONTENT_SYSTEM = (
    "Ты извлекаешь признаки финансового мошенничества из текста (подпись, субтитры, "
    "распознанная речь и текст с кадров). Верни СТРОГО JSON с булевыми полями "
    "(true/false), без пояснений:\n"
    "promises_returns — обещание прибыли / высокой или гарантированной доходности;\n"
    "has_referral — реферальная схема, «пригласи друзей», бонус за приглашение;\n"
    "has_license — упоминание лицензии / регулятора / легальности;\n"
    "gambling_content — казино, ставки, слоты, букмекер;\n"
    "aggressive_investment — агрессивный призыв вложить срочно: «успей», «последний "
    "шанс», «действуй сейчас», «не упусти», давление и спешка;\n"
    "hidden_engagement — скрытое вовлечение: увод в личку/закрытый чат/бота, «напиши "
    "в ЛС», секретный канал, приватная группа, скрытая воронка."
)


def claim_prompt(text: str) -> tuple[str, str]:
    return _SYSTEM, f"Текст:\n{text}"


def content_facts_prompt(text: str) -> tuple[str, str]:
    return _CONTENT_SYSTEM, f"Текст:\n{text}"


def _parse_flags(raw: str, keys: tuple[str, ...]) -> dict:
    """Robustly parse the LLM's JSON for the given boolean keys. Failure -> all False."""
    flags = {k: False for k in keys}
    if not raw:
        return flags
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return flags
    try:
        data = json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return flags
    if not isinstance(data, dict):
        return flags
    for k in keys:
        flags[k] = bool(data.get(k, False))
    return flags


def parse_claims(raw: str) -> dict:
    """Robustly parse the LLM's JSON. Any failure -> all False (fail-safe)."""
    return _parse_flags(raw, CLAIM_KEYS)


def parse_content_facts(raw: str) -> dict:
    """Parse the 4 claim flags + 2 intensifier signals (fail-safe -> all False)."""
    return _parse_flags(raw, CONTENT_FACT_KEYS)


# High-precision keyword cues — a deterministic fallback that reinforces the LLM and,
# crucially, keeps extraction working when the LLM is rate-limited (429) or offline:
# an explicit caption like «бонусы от букмекера 1xBET» still raises the right flags.
_KW_GAMBLING = (
    "казино", "casino", "ставк", "слот", "slot", "букмекер", "betting", "рулетк",
    "покер", "poker", "джекпот", "jackpot", "1xbet", "1хбет", "1x bet", "melbet",
    "mostbet", "fonbet", "winline", "ставки на спорт", "игровой счет", "игровой счёт",
)
_KW_PROMISES = (
    "гарантирован", "пассивный доход", "высокий доход", "доходность", "прибыл",
    "профит", "заработок", "заработай", "удвой", "умнож", "x100", "х100",
    "% в месяц", "процентов в месяц", "300%", "вывод средств", "выводи деньги",
)
_KW_REFERRAL = (
    "реферал", "referral", "пригласи друз", "приглашай друз", "бонус за друг",
    "по моей ссылке", "по реферальной", "приведи друг",
)
_KW_AGGRESSIVE = (
    "успей", "срочно", "последний шанс", "не упусти", "действуй сейчас",
    "прямо сейчас", "только сегодня", "ограниченное предложение", "спеши",
)
_KW_HIDDEN = (
    "напиши в лс", "пиши в лс", "в личк", "в директ", "закрытый канал",
    "закрытый чат", "приватн", "секретн", "t.me/", "телеграм-бот", "телеграм бот",
)


def keyword_facts(text: str) -> dict:
    """Deterministic high-precision keyword fallback for the 6 content facts.

    `has_license` is intentionally NOT inferred here — a wrong True would *lower*
    risk; that protective flag stays with the LLM + АРРФР registry."""
    t = (text or "").lower()

    def has(words: tuple[str, ...]) -> bool:
        return any(w in t for w in words)

    flags = {k: False for k in CONTENT_FACT_KEYS}
    flags["gambling_content"] = has(_KW_GAMBLING)
    flags["promises_returns"] = has(_KW_PROMISES)
    flags["has_referral"] = has(_KW_REFERRAL)
    flags["aggressive_investment"] = has(_KW_AGGRESSIVE)
    flags["hidden_engagement"] = has(_KW_HIDDEN)
    return flags


def extract_claims(llm, text: str) -> dict:
    """LLM claim flags, OR-reinforced by keyword cues (robust to 429 / LLM down)."""
    if not text:
        return {k: False for k in CLAIM_KEYS}
    kw = keyword_facts(text)
    try:
        system, user = claim_prompt(text)
        llm_flags = parse_claims(llm.complete(system, user))
    except Exception:  # noqa: BLE001 — never let extraction break the pipeline
        llm_flags = {k: False for k in CLAIM_KEYS}
    return {k: bool(llm_flags.get(k) or kw.get(k)) for k in CLAIM_KEYS}


def extract_content_facts(llm, text: str) -> dict:
    """6 per-video facts from the LLM, OR-reinforced by keyword cues (robust to 429)."""
    if not text:
        return {k: False for k in CONTENT_FACT_KEYS}
    kw = keyword_facts(text)
    try:
        system, user = content_facts_prompt(text)
        llm_flags = parse_content_facts(llm.complete(system, user))
    except Exception:  # noqa: BLE001 — never let extraction break the pipeline
        llm_flags = {k: False for k in CONTENT_FACT_KEYS}
    return {k: bool(llm_flags.get(k) or kw.get(k)) for k in CONTENT_FACT_KEYS}


def aggregate_claims(items: list[dict]) -> dict:
    """OR claim flags across a target's content (any post triggering a flag counts)."""
    out = {k: False for k in CLAIM_KEYS}
    for it in items:
        for k in CLAIM_KEYS:
            out[k] = out[k] or bool(it.get(k, False))
    return out
