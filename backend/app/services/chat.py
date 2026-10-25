"""AI assistant for the analyst — grounded chat over the platform.

Uses the same AI provider abstraction as the rest of SafeNet KZ, so it honours
AI_PROVIDER (mock → fully offline canned answers; openai/local → live LLM). The
prompt is grounded with a few live counts so answers reference real state, and
the LLM is told never to invent numbers. Stateless: short history is folded in.
"""
from __future__ import annotations

_SYSTEM = (
    "Ты — AI-ассистент аналитика платформы SafeNet KZ: признаки платных розыгрышей, скрытой "
    "рекламы онлайн-казино и финансовых пирамид в соцсетях и мессенджерах Казахстана. "
    "Отвечай КРАТКО, по-русски, по делу. Помогаешь объяснять риск-оценку и признаки, "
    "подсказывать по разделам (Проверка контента, Материалы, Досье, Граф связей, Метрики, "
    "Мониторинг). Риск считает детерминированный движок по трекам; LLM лишь находит признаки "
    "с дословными цитатами. Система НЕ объявляет схему незаконной — она показывает признаки "
    "возможного нарушения для проверки специалистом. Не выдумывай цифры, которых нет в контексте."
)


def context_line(session) -> str:
    """A compact live snapshot folded into the prompt so answers are grounded."""
    try:
        from app.db.models import ContentRisk, WatchTarget
        materials = session.query(ContentRisk).count()
        high = session.query(ContentRisk).filter(ContentRisk.score >= 65).count()
        watched = session.query(WatchTarget).filter_by(active=True).count()
        return (f"Сейчас в системе: материалов={materials}, высокий риск (≥65)={high}, "
                f"аккаунтов под наблюдением={watched}.")
    except Exception:  # noqa: BLE001 — context is best-effort
        return "Контекст системы недоступен."


def _mock_answer(message: str, ctx: str) -> str:
    """Offline canned assistant (AI_PROVIDER=mock) — keyword-routed, grounded."""
    m = (message or "").lower()
    if any(k in m for k in ("сколько", "материал", "статист", "высок", "обзор")):
        return f"{ctx} Подробнее — на «Главной» и в «Материалах» (сортировка риск × охват)."
    if "риск" in m or "балл" in m or "оцен" in m:
        return ("Риск = взвешенная сумма 6 факторов ТЗ (обещание дохода 25, реферал 20, "
                "повтор схемы 20, подозрительные связи 15, гемблинг 10, нет лицензии 10). "
                "LLM извлекает факты, число считает детерминированный движок — каждый балл "
                "трассируется к доказательству.")
    if "охват" in m or "приоритет" in m:
        return ("Охват (просмотры/лайки) не входит в риск, а задаёт приоритет: "
                "priority = риск × (1 + охват). Вирусный ролик с тем же риском — выше в очереди.")
    if "граф" in m or "связ" in m or "сет" in m:
        return ("Граф сети связывает аккаунты по общим кошелькам/Telegram (Neo4j), выделяет "
                "сообщества и организаторов. «Money Flow» трассирует кошелёк → биржа.")
    if any(k in m for k in ("привет", "здравств", "что ты", "помощ", "умеешь")):
        return ("Привет! Я ассистент аналитика SafeNet KZ. Спроси про риск-оценку, охват, граф связей, "
                "Money Flow или как пользоваться разделами. " + ctx)
    return ("Я помогаю по платформе SafeNet KZ: риск-оценка, признаки, граф связей, Money Flow, "
            "приоритизация материалов. Уточни вопрос. " + ctx)


def answer(session, message: str, history: list[tuple[str, str]] | None = None) -> str:
    from app.services import runtime_config as rc

    ctx = context_line(session)
    if rc.get_value("ai_provider") == "mock":
        return _mock_answer(message, ctx)

    convo = "\n".join(f"{r}: {c}" for r, c in (history or [])[-6:])
    user = f"Контекст: {ctx}\n\n{convo}\nuser: {message}\nassistant:"
    try:
        from app.services.ai.factory import get_llm
        return (get_llm().complete(_SYSTEM, user) or "").strip() or _mock_answer(message, ctx)
    except Exception:  # noqa: BLE001 — provider down/429 -> graceful offline answer
        return _mock_answer(message, ctx)
