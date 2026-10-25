"""Runtime-configurable settings (DB-backed key→value), editable from the UI.

One registry describes every tunable knob (group, type, bounds, help). Each value
falls back to its env/`settings` default when there's no DB row (or the DB is
unavailable), so the system behaves identically out of the box and unit tests that
monkeypatch `settings` keep working. Consumers read effective values via
`get_value`; the API lists/updates them via `REGISTRY`.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.db import settings_repo as repo
from app.db.session import get_session


@dataclass(frozen=True)
class Setting:
    group: str
    key: str
    type: str                       # "int" | "float" | "bool" | "str"
    label: str
    help: str = ""
    min: float | None = None
    max: float | None = None
    options: tuple[str, ...] | None = None


# Defaults are read lazily from `settings` so a monkeypatch in tests is honoured
# and there's a single source of truth for the out-of-the-box value.
_DEFAULTS = {
    "collect_video_limit": lambda: settings.collect_video_limit,
    "video_frames": lambda: settings.video_frames,
    "ai_provider": lambda: settings.ai_provider,
    "ai_chat_model": lambda: settings.openai_chat_model,
    "ai_vision_model": lambda: settings.openai_vision_model,
    "ai_max_retries": lambda: settings.ai_max_retries,
    "ai_retry_base_seconds": lambda: settings.ai_retry_base_seconds,
    "watchlist_enabled": lambda: False,           # off until started by the analyst
    "watchlist_sweep_seconds": lambda: settings.watchlist_sweep_seconds,
    "alert_on_high_risk": lambda: True,
    "alert_min_score": lambda: 65,
    "dev_mode": lambda: False,
    "mock_delay_seconds": lambda: settings.mock_delay_seconds,
    "mock_money_flow": lambda: settings.mock_money_flow,
    "mock_hunter": lambda: settings.mock_hunter,
    "safenet_llm_assist": lambda: True,
}

REGISTRY: list[Setting] = [
    Setting("Сбор", "collect_video_limit", "int", "Лимит видео за один сбор",
            "Сколько последних роликов скачивать с аккаунта / по ключевому слову.", min=1, max=200),
    Setting("Сбор", "video_frames", "int", "Кадров на видео для распознавания",
            "Сколько кадров сэмплировать для vision/OCR (больше — точнее, но дороже).", min=1, max=12),

    Setting("AI / ресурс", "ai_provider", "str", "AI-провайдер (откуда брать ресурс)",
            "openai / anthropic — внешний API (только синтетика!); local — self-hosted; "
            "mock — полностью офлайн (без сети и внешних API: детерминированные факты, "
            "эмбеддинги, vision/OCR и mock-загрузка — для демо).",
            options=("openai", "anthropic", "local", "mock")),
    Setting("AI / ресурс", "ai_chat_model", "str", "Модель LLM (факты и нарратив)",
            "Напр. gpt-4o. Действует для openai-провайдера."),
    Setting("AI / ресурс", "ai_vision_model", "str", "Модель vision / OCR",
            "Напр. gpt-4o. Распознавание объектов и текста на кадрах."),

    Setting("AI / ресурс", "safenet_llm_assist", "bool", "LLM-помощник для поиска признаков",
            "Кроме детерминированных правил, LLM ищет перефразированные признаки (сленг, "
            "казахский). Каждая находка обязана содержать дословную цитату из текста — иначе "
            "отбрасывается. Балл всё равно считает детерминированный движок."),

    Setting("Ретраи", "ai_max_retries", "int", "Попыток при 429 / 5xx",
            "Сколько раз повторить запрос к AI при лимите/временной ошибке.", min=0, max=10),
    Setting("Ретраи", "ai_retry_base_seconds", "float", "Базовая пауза ретрая, сек",
            "Стартовая задержка backoff (1→2→4…). Retry-After от провайдера приоритетнее.",
            min=0, max=60),

    Setting("Мониторинг", "watchlist_enabled", "bool", "Автосбор включён",
            "Главный выключатель планового сбора с аккаунтов под наблюдением."),
    Setting("Мониторинг", "watchlist_sweep_seconds", "int", "Интервал автосбора, сек",
            "Как часто планировщик перевыкачивает наблюдаемые цели (мин. 60).", min=60, max=86400),
    Setting("Мониторинг", "alert_on_high_risk", "bool", "Алерт при высоком риске (радар)",
            "Слать уведомление по ЛЮБОМУ найденному ролику с риском ≥ порога, а не "
            "только по аккаунтам под наблюдением. Так радар сам находит мошенничество."),
    Setting("Мониторинг", "alert_min_score", "int", "Порог риска для алерта",
            "Минимальный балл (0–100), при котором найденный контент даёт уведомление. "
            "65 = HIGH и выше.", min=0, max=100),

    Setting("Демо / Dev", "mock_hunter", "bool", "Мокать Хантер",
            "Хантер синтезирует и сразу оценивает находки локально (без сети и OpenAI) — "
            "автономная охота надёжно находит аккаунты даже на живом AI-провайдере. "
            "Реальный поиск по соцсетям хрупкий, поэтому для демо держите включённым."),
    Setting("Демо / Dev", "mock_money_flow", "bool", "Мокать Money Flow",
            "Показывать синтетическую on-chain трассировку (кошелёк → биржа) даже на "
            "живом AI-провайдере — у демо-аккаунтов нет реальной on-chain истории. "
            "Не требует Etherscan-ключа."),
    Setting("Демо / Dev", "mock_delay_seconds", "float", "Задержка mock-анализа, сек",
            "Искусственная пауза при анализе видео в режиме AI-провайдер=mock — чтобы "
            "обработка выглядела реалистично (а не мгновенно). 0 — без задержки.",
            min=0, max=30),
    Setting("Демо / Dev", "dev_mode", "bool", "Демо-режим (мок-аналитика)",
            "Включение наполняет систему готовой аналитикой по демо-рилсу "
            "(аккаунт ami_d0maru): риск, идентификаторы, TG-граф связей, алерт — "
            "без Instagram-куки и без OpenAI. Выключение удаляет мок-данные."),
]
_BY_KEY = {s.key: s for s in REGISTRY}


class UnknownSetting(KeyError):
    pass


def _coerce(t: str, raw):
    if t == "int":
        return int(raw)
    if t == "float":
        return float(raw)
    if t == "bool":
        return str(raw).lower() in ("1", "true", "yes", "on")
    return str(raw)


def default(key: str):
    return _DEFAULTS[key]()


def get_value(key: str):
    """Effective value: DB override if present & valid, else the env/`settings` default."""
    s = _BY_KEY.get(key)
    if s is None:
        raise UnknownSetting(key)
    try:
        gen = get_session()
        session = next(gen)
        try:
            raw = repo.get(session, key)
        finally:
            gen.close()
        if raw is not None:
            return _coerce(s.type, raw)
    except Exception:  # noqa: BLE001 — no DB (unit tests) or bad value -> fall back to default
        pass
    return default(key)


def validate(key: str, value) -> str:
    """Coerce + range-check a candidate value; return the string to persist."""
    s = _BY_KEY.get(key)
    if s is None:
        raise UnknownSetting(key)
    try:
        v = _coerce(s.type, value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key}: invalid {s.type} value {value!r}") from exc
    if s.options and str(v) not in s.options:
        raise ValueError(f"{key}: must be one of {list(s.options)}")
    if s.type in ("int", "float"):
        if s.min is not None and v < s.min:
            raise ValueError(f"{key}: must be >= {s.min}")
        if s.max is not None and v > s.max:
            raise ValueError(f"{key}: must be <= {s.max}")
    if s.type == "bool":
        return "true" if v else "false"
    return str(v)


def describe(session) -> list[dict]:
    """List every setting with its current effective value (for the settings UI)."""
    out = []
    for s in REGISTRY:
        raw = repo.get(session, s.key)
        try:
            value = _coerce(s.type, raw) if raw is not None else default(s.key)
        except (TypeError, ValueError):
            value = default(s.key)
        out.append({
            "group": s.group, "key": s.key, "type": s.type, "label": s.label,
            "help": s.help, "min": s.min, "max": s.max,
            "options": list(s.options) if s.options else None,
            "value": value, "is_default": raw is None,
        })
    return out


def apply(session, updates: dict) -> list[dict]:
    """Validate + persist a batch of {key: value}. Raises ValueError on bad input."""
    for key, value in updates.items():
        repo.set(session, key, validate(key, value))
    # Side-effect: toggling dev_mode seeds/clears the mock demo dataset.
    if "dev_mode" in updates:
        on = validate("dev_mode", updates["dev_mode"]) == "true"
        try:
            from app.services import dev_mock
            dev_mock.seed_mock(session) if on else dev_mock.clear_mock(session)
        except Exception:  # noqa: BLE001 — never fail the settings save on mock seed issues
            pass
    return describe(session)
