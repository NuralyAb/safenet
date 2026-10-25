"""SafeNet KZ: metrics, methodology, track summary and demo data."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session

router = APIRouter()

DATASETS = {
    "blind": "Независимая слепая выборка (написана отдельным автором, не видевшим правил)",
    "holdout": "Отложенная выборка №2 (после v2; использовалась для разбора ошибок)",
    "test": "Тестовая выборка №1 (ручная разметка; использовалась для разбора ошибок)",
    "dev": "Выборка настройки (шаблоны)",
}


@router.get("/metrics")
def metrics(dataset: str = "blind", principal: Principal = Depends(require_role(Role.ANALYST))) -> dict:
    """Precision / recall / FPR of the rules-only detector on a bundled labelled set."""
    from app.services.safenet.evaluation import DATA_DIR, cached_report

    if dataset not in DATASETS or not (DATA_DIR / f"{dataset}.jsonl").exists():
        raise HTTPException(status_code=404, detail="Нет такой выборки")
    report = dict(cached_report(dataset))
    report["dataset"] = dataset
    report["title"] = DATASETS[dataset]
    report["available"] = [{"id": k, "title": v} for k, v in DATASETS.items()
                           if (DATA_DIR / f"{k}.jsonl").exists()]
    return report


@router.get("/methodology")
def methodology(principal: Principal = Depends(require_role(Role.ANALYST))) -> dict:
    """Every signal, its weight per track, the gates and the level thresholds."""
    from app.services.safenet import lexicon, scoring

    return {
        "tracks": lexicon.TRACK_LABELS,
        "signals": lexicon.catalog(),
        "weights": scoring.TRACK_WEIGHTS,
        "levels": {"HIGH": scoring.HIGH, "MEDIUM": scoring.MEDIUM},
        "flag_threshold": scoring.FLAG_THRESHOLD,
        "extra": lexicon.EXTRA_LABELS,
        "disclaimer": scoring.DISCLAIMER,
        "gates": [
            "Розыгрыш: без признака платного участия или без темы розыгрыша — балл ≤ 25; "
            "взнос без случайного выбора и без перевода на личную карту (турнир) — ≤ 35; "
            "механика бесплатного конкурса — ×0.5.",
            "Казино: без игровой лексики/бренда — ≤ 20 (или ≤ 50 при нативной рекламе со ссылкой); "
            "упоминание игр без продвижения — ≤ 35; оператор в реестре лицензий — ×0.5.",
            "Пирамида: без обещания нереалистичной доходности и без дохода от привлечения — ≤ 30 "
            "(×0.8 при реферальном сборе денег).",
            "Предупреждение/новость о мошенничестве без ссылки, карты, телефона или призыва — ×0.4.",
        ],
    }


@router.get("/summary")
def summary(principal: Principal = Depends(require_role(Role.ANALYST)),
            session: Session = Depends(get_session)) -> dict:
    """Review-queue counts by track × level (dashboard)."""
    from app.db.models import ContentRisk

    rows = (session.query(ContentRisk.track, ContentRisk.threat_level, func.count())
            .group_by(ContentRisk.track, ContentRisk.threat_level).all())
    out: dict = {}
    for track, level, n in rows:
        out.setdefault(track or "none", {}).setdefault(level, 0)
        out[track or "none"][level] += n
    pending = session.query(func.count()).select_from(ContentRisk).filter(
        ContentRisk.disposition == "pending", ContentRisk.threat_level.in_(("MEDIUM", "HIGH"))).scalar()
    return {"by_track": out, "pending_review": pending}


@router.get("/demo-chats")
def demo_chats(principal: Principal = Depends(require_role(Role.ANALYST))) -> list[dict]:
    from app.services.safenet.demo import demo_chat_list
    return demo_chat_list()


@router.post("/rescore")
def rescore(principal: Principal = Depends(require_role(Role.ANALYST)),
            session: Session = Depends(get_session)) -> dict:
    """Re-score all queued materials with the current SafeNet engine (keeps dispositions)."""
    from app.services.safenet.demo import rescore_all

    record_action(session, principal.subject, "safenet.rescore", "all")
    return rescore_all(session)


@router.post("/demo-seed")
def demo_seed(reset: bool = False, principal: Principal = Depends(require_role(Role.ANALYST)),
              session: Session = Depends(get_session)) -> dict:
    """Load the synthetic SafeNet demo (accounts, networks, group chats)."""
    from app.services.safenet.demo import seed

    record_action(session, principal.subject, "safenet.demo_seed", f"reset={reset}")
    return seed(session, reset=reset)
