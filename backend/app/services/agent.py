"""Tool-calling assistant — the chat can DO things, not just talk.

The LLM (or, in mock mode, a deterministic keyword router) picks ONE tool + args;
the tool runs against our own services and returns FACTUAL data; the reply is then
templated from that data (never the LLM inventing numbers). Some tools also return
a UI `action` so the frontend can navigate (open the graph for an account, etc.).

Provider-agnostic: tool selection goes through get_llm().complete returning strict
JSON — same defensive parse we use for claims. Any failure degrades to plain chat.
"""
from __future__ import annotations

import json
import re

# Tool catalog shown to the LLM for selection.
_CATALOG = (
    'Инструменты. Верни СТРОГО JSON: {"tool": <имя|null>, "args": {...}}.\n'
    '- stats — общая статистика системы. args: {}\n'
    '- top_materials — топ рискованных материалов. args: {"limit": число (необяз.)}\n'
    '- account_summary — сводка по аккаунту. args: {"account": "@handle"}\n'
    '- analyze_url — проанализировать видео по ссылке. args: {"url": "http..."}\n'
    '- hunt — автономно искать мошеннические схемы (генерит запросы и запускает сбор). args: {"count": число (необяз.)}\n'
    '- open_view — открыть раздел интерфейса. args: {"view": '
    '"dashboard|materials|triage|graph|flow|radar|watchlist|dossier", "target": "@handle (необяз.)"}\n'
    'Если это общий вопрос (объяснить/помочь) — {"tool": null}.'
)

_VIEWS = {"dashboard", "materials", "triage", "graph", "flow", "radar", "watchlist", "dossier", "analyze"}
_HANDLE = re.compile(r"@[\w.]+")
_URL = re.compile(r"https?://\S+")


# ---- tool selection ---------------------------------------------------------
def _choose_mock(message: str) -> dict:
    m = (message or "").lower()
    url = _URL.search(message or "")
    if url:
        return {"tool": "analyze_url", "args": {"url": url.group(0)}}
    if any(k in m for k in ("охот", "hunt", "найди мошен", "ищи мошен", "просканируй", "поищи схем")):
        return {"tool": "hunt", "args": {}}
    handle = _HANDLE.search(message or "")
    if "граф" in m:
        return {"tool": "open_view", "args": {"view": "graph", "target": handle.group(0) if handle else ""}}
    if "money" in m or "поток" in m or "кошел" in m:
        return {"tool": "open_view", "args": {"view": "flow", "target": handle.group(0) if handle else ""}}
    if "радар" in m:
        return {"tool": "open_view", "args": {"view": "radar"}}
    if handle and any(k in m for k in ("аккаунт", "досье", "сводк", "профил", "что по")):
        return {"tool": "account_summary", "args": {"account": handle.group(0)}}
    if "топ" in m or "опасн" in m or ("материал" in m and "сколько" not in m):
        return {"tool": "top_materials", "args": {"limit": 5}}
    if any(k in m for k in ("статист", "сколько", "обзор", "сводка систем")):
        return {"tool": "stats", "args": {}}
    if handle:
        return {"tool": "account_summary", "args": {"account": handle.group(0)}}
    return {"tool": None, "args": {}}


def _choose_llm(message: str, history: list[tuple[str, str]]) -> dict:
    from app.services.ai.factory import get_llm

    convo = "\n".join(f"{r}: {c}" for r, c in (history or [])[-4:])
    raw = get_llm().complete(_CATALOG, f"{convo}\nuser: {message}") or ""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {"tool": None, "args": {}}
    try:
        data = json.loads(raw[start:end + 1])
        return {"tool": data.get("tool"), "args": data.get("args") or {}}
    except (json.JSONDecodeError, ValueError):
        return {"tool": None, "args": {}}


# ---- tools ------------------------------------------------------------------
def _t_stats(session, _args) -> dict:
    from app.services.chat import context_line
    return {"reply": context_line(session), "action": {"type": "navigate", "view": "dashboard"}}


_LEVEL_RU = {"HIGH": "высокий", "CRITICAL": "высокий", "MEDIUM": "средний", "LOW": "низкий"}
_TRACK_RU = {"lottery": "платный розыгрыш", "casino": "скрытое казино", "pyramid": "пирамида"}


def _fmt_views(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} млн"
    if n >= 1_000:
        return f"{n / 1_000:.0f} тыс."
    return str(n)


def _t_top_materials(session, args) -> dict:
    from app.db import risk_repo
    limit = int(args.get("limit") or 5)
    rows = risk_repo.list_content_for_triage(session)[:limit]
    if not rows:
        return {"reply": "Материалов пока нет — проверьте пост, скриншот или группу."}
    lines = [f"{i+1}. {r.author or r.content_id[:10]} — {_TRACK_RU.get(r.track, 'без трека')}, "
             f"риск {r.score} ({_LEVEL_RU.get(r.threat_level, r.threat_level)}), охват {_fmt_views(r.views)}"
             for i, r in enumerate(rows)]
    return {"reply": "Топ материалов по приоритету:\n" + "\n".join(lines),
            "action": {"type": "navigate", "view": "materials"}}


def _t_account_summary(session, args) -> dict:
    from app.db.models import ContentRisk, RiskAssessment
    acc = (args.get("account") or "").strip()
    if not acc:
        return {"reply": "Укажи аккаунт, например: сводка по @handle."}
    # accounts are stored both as «@handle» and «handle» depending on the source
    variants = list(dict.fromkeys([acc, acc.lstrip("@"), "@" + acc.lstrip("@")]))
    risks = session.query(ContentRisk).filter(ContentRisk.author.in_(variants)).all()
    a = session.query(RiskAssessment).filter(RiskAssessment.target.in_(variants)).first()
    if not risks and a is None:
        return {"reply": f"По {acc} данных нет. Проверьте его посты или соберите материалы."}
    if risks:
        acc = risks[0].author
    scores = [r.score for r in risks]
    tracks = sorted({_TRACK_RU.get(r.track, "") for r in risks if r.track and r.score >= 40} - {""})
    parts = [f"{acc}: материалов — {len(risks)}"]
    if scores:
        top = max(risks, key=lambda r: r.score)
        parts.append(f"максимальный риск {top.score} ({_LEVEL_RU.get(top.threat_level, top.threat_level)})")
        parts.append(f"суммарный охват {_fmt_views(sum(r.views for r in risks))}")
    if tracks:
        parts.append("треки: " + ", ".join(tracks))
    if a:
        parts.append(f"оценка аккаунта {a.score} ({_LEVEL_RU.get(a.threat_level, a.threat_level)})")
    return {"reply": ", ".join(parts) + ".",
            "action": {"type": "navigate", "view": "dossier", "target": acc}}


def _t_analyze_url(session, args) -> dict:
    url = (args.get("url") or "").strip()
    if not url:
        return {"reply": "Дай ссылку на видео для анализа."}
    try:
        from app.services.adhoc import DownloadFailed, fetch_media, run_analysis
        try:
            p = fetch_media(url)
        except DownloadFailed as e:
            return {"reply": str(e)}
        r = run_analysis(p.get("media"), source=p["source"], url=url, caption=p["caption"],
                         author=p["author"], images=p["images"], reach=p.get("reach"))
        risk = r["risk"]
        flags = [k for k, v in r.get("claims", {}).items() if v]
        return {"reply": f"Анализ {p.get('author') or url}: риск {risk['score']} ({risk['threat_level']}). "
                         f"Признаки: {', '.join(flags) or 'не выявлены'}. Охват: {r.get('reach', {}).get('views', 0)}.",
                "action": {"type": "navigate", "view": "materials"}}
    except Exception:  # noqa: BLE001
        return {"reply": "Не удалось проанализировать ссылку. Проверь её или загрузи файл."}


def _t_open_view(session, args) -> dict:
    view = (args.get("view") or "dashboard").strip()
    if view not in _VIEWS:
        view = "dashboard"
    target = (args.get("target") or "").strip()
    label = {"graph": "граф сети", "flow": "Money Flow", "radar": "радар", "materials": "материалы",
             "dossier": "досье", "triage": "триаж", "watchlist": "мониторинг",
             "dashboard": "главную"}.get(view, view)
    extra = f" для {target}" if target else ""
    return {"reply": f"Открываю {label}{extra}.",
            "action": {"type": "navigate", "view": view, "target": target}}


def _t_hunt(session, args) -> dict:
    from app.services.hunter import run_hunt
    out = run_hunt(session, count=int(args.get("count") or 6))
    qs = ", ".join(f"«{q}»" for q in out["queries"][:4])
    return {"reply": f"Запустил автономную охоту: {out['count']} запросов ({qs}…). "
                     "Найденные ролики с риском появятся в «Материалах» и «Радаре».",
            "action": {"type": "navigate", "view": "radar"}}


_TOOLS = {
    "stats": _t_stats,
    "top_materials": _t_top_materials,
    "account_summary": _t_account_summary,
    "analyze_url": _t_analyze_url,
    "open_view": _t_open_view,
    "hunt": _t_hunt,
}


def run(session, message: str, history: list[tuple[str, str]] | None = None) -> dict:
    """Pick a tool and run it, else fall back to a plain grounded chat answer."""
    from app.services import runtime_config as rc

    try:
        choice = _choose_mock(message) if rc.get_value("ai_provider") == "mock" \
            else _choose_llm(message, history or [])
    except Exception:  # noqa: BLE001 — LLM down / no quota -> deterministic router
        choice = {"tool": None, "args": {}}
    if not choice.get("tool"):                 # the keyword router still understands commands
        choice = _choose_mock(message)

    tool = choice.get("tool")
    if tool in _TOOLS:
        try:
            return _TOOLS[tool](session, choice.get("args") or {})
        except Exception:  # noqa: BLE001 — tool failure -> plain chat
            pass

    from app.services.chat import answer
    return {"reply": answer(session, message, history)}
