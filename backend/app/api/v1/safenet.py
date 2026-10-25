"""SafeNet KZ: metrics, methodology, track summary and demo data."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session

router = APIRouter()

DATASETS = {
    "blind2": "Независимая слепая выборка №2 — главная оценка v4 (отдельный автор, сложнее: числа прописью, "
              "эфиры, OCR, казахские чаты; прогнана один раз)",
    "blind": "Независимая слепая выборка №1 (оценка v3; после этого видена разработчиком — для v4 полуслепая)",
    "holdout": "Отложенная выборка №2 (после v2; использовалась для разбора ошибок)",
    "test": "Тестовая выборка №1 (ручная разметка; использовалась для разбора ошибок)",
    "dev": "Выборка настройки (шаблоны)",
}


@router.get("/metrics")
def metrics(dataset: str = "blind2", model: bool = True,
            principal: Principal = Depends(require_role(Role.ANALYST))) -> dict:
    """Precision / recall / FPR on a bundled labelled set — rules only or rules + learned layer."""
    from app.services.safenet.evaluation import DATA_DIR, cached_report
    from app.services.safenet.model import TRAIN_SETS

    if dataset not in DATASETS or not (DATA_DIR / f"{dataset}.jsonl").exists():
        raise HTTPException(status_code=404, detail="Нет такой выборки")
    report = dict(cached_report(dataset, use_model=model))
    report["dataset"] = dataset
    report["title"] = DATASETS[dataset]
    report["mode"] = "rules+model" if model else "rules"
    report["training_set"] = bool(model and dataset in TRAIN_SETS)
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


@router.get("/campaigns")
def campaigns(principal: Principal = Depends(require_role(Role.ANALYST)),
              session: Session = Depends(get_session)) -> list[dict]:
    """Networks of accounts linked by shared identifiers / copy-paste texts, by priority."""
    from app.services.safenet.campaigns import build_campaigns
    return build_campaigns(session)


@router.get("/insights")
def insights(principal: Principal = Depends(require_role(Role.ANALYST)),
             session: Session = Depends(get_session)) -> dict:
    """Emerging wording not covered by the lexicon + signal quality from analyst decisions."""
    from app.services.safenet.insights import emerging_terms, feedback_quality
    return {"emerging": emerging_terms(session), "feedback": feedback_quality(session)}


MAX_BULK_BYTES = 30 * 1024 * 1024


@router.post("/bulk")
def bulk_check(
    file: UploadFile | None = File(None),
    demo: int = Form(0),
    persist: bool = Form(True),
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Score a CSV / JSONL / TXT of posts (or a synthetic demo feed of `demo` posts)."""
    from app.services.safenet.bulk import MAX_ROWS, demo_rows, parse_rows, run_bulk

    if demo:
        rows = demo_rows(min(max(demo, 100), MAX_ROWS))
        label = "demo-feed"
    elif file is not None:
        raw = file.file.read(MAX_BULK_BYTES + 1)
        if len(raw) > MAX_BULK_BYTES:
            raise HTTPException(status_code=413, detail="Файл слишком большой (макс. 30 МБ)")
        rows = parse_rows(raw, file.filename or "")
        label = (file.filename or "bulk")[:60]
    else:
        raise HTTPException(status_code=400, detail="Загрузите файл или укажите demo")
    if not rows:
        raise HTTPException(status_code=422, detail="Не найдено ни одного текста (нужен столбец/поле text)")
    record_action(session, principal.subject, "safenet.bulk", f"{label}:{len(rows)}")
    return run_bulk(rows, session=session, persist=persist, label=label)


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
