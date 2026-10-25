"""Deterministic, explainable per-track risk scoring (SafeNet KZ).

detect() finds SIGNALS; this module turns them into a 0–100 score per track with a
fixed, documented formula — the LLM never assigns the number (ADR-0003 invariant).

    track_score = Σ weight(signal) × strength(signal)          (signals of that track)
                  then GATES (cap when the track's core sign is absent)
                  then MITIGATION (free-contest mechanics, anti-fraud warning, licence)
    final       = max over tracks;  level: HIGH ≥ 65, MEDIUM ≥ 40, else LOW

Gates are what keep false positives low: a paid seminar is not a lottery (no
giveaway context), a bank deposit at 15% годовых is not a pyramid (no unrealistic
return), sports news about bets is not a casino ad (no promotion signal).

Every adjustment is written into the breakdown as its own line with a negative
contribution, so Σ contributions == score and every point is traceable.
"""
from __future__ import annotations

from app.services import risk_engine
from app.services.safenet import lexicon
from app.services.safenet.detector import SOURCE_LABELS, VIEW_LABELS, Detection, Hit

HIGH, MEDIUM = 65, 40
FLAG_THRESHOLD = MEDIUM          # «помечено для ручной проверки» (used for metrics)

# Per-track weights. Shared signals (personal transfer) count in lottery and pyramid.
TRACK_WEIGHTS: dict[str, dict[str, int]] = {
    "lottery": {
        "lottery.paid_entry": 40, "lottery.random_draw": 20, "lottery.organizer_income": 20,
        "lottery.giveaway": 10, "lottery.series": 10, "shared.personal_transfer": 15,
        "network.links": 10,
    },
    "casino": {
        "casino.gambling": 25, "casino.brand": 25, "casino.native_win": 25, "casino.promo_code": 20,
        "casino.tracking_link": 15, "casino.call_to_action": 15, "casino.stream": 10,
        "casino.proxy_channel": 10, "visual.gambling": 15, "network.links": 10,
    },
    "pyramid": {
        "pyramid.unrealistic_return": 40, "pyramid.recruitment_income": 30, "shared.personal_transfer": 20,
        "pyramid.referral": 20, "pyramid.entry_payment": 10,
        "pyramid.urgency": 15, "pyramid.payout_proofs": 10, "pyramid.structure_roles": 10,
        "pyramid.closed_chat": 5, "group.template_messages": 10, "group.proof_flood": 10,
        "group.organizer_curators": 10, "network.links": 10,
    },
}

CASINO_PROMOTION = ("casino.native_win", "casino.promo_code", "casino.tracking_link",
                    "casino.call_to_action", "casino.stream", "casino.proxy_channel")
# A warning post loses its discount only when it also tells people WHERE to pay or
# click. Words («промокоды», «перевести на карту», «зеркала») appear in warnings too;
# a concrete link / card / phone / promo code / call-to-action does not.
DIRECT_CALL = ("casino.call_to_action",)
_LINK_IDS = ("short_links", "telegram", "whatsapp", "cards", "promo_codes", "phones")

DISCLAIMER = ("Система не объявляет схему незаконной: она показывает признаки возможного "
              "нарушения. Законность проверяет специалист с учётом законодательства РК.")


def level_for(score: int) -> risk_engine.ThreatLevel:
    if score >= HIGH:
        return risk_engine.ThreatLevel.HIGH
    if score >= MEDIUM:
        return risk_engine.ThreatLevel.MEDIUM
    return risk_engine.ThreatLevel.LOW


LEVEL_RU = {"LOW": "низкий", "MEDIUM": "средний", "HIGH": "высокий"}


def recommendation_for(level: risk_engine.ThreatLevel, track: str) -> str:
    name = lexicon.TRACK_LABELS.get(track, "")
    if level == risk_engine.ThreatLevel.HIGH:
        return f"Высокий риск ({name.lower()}): приоритетная ручная проверка специалистом."
    if level == risk_engine.ThreatLevel.MEDIUM:
        return f"Средний риск ({name.lower()}): проверить контекст вручную."
    return "Низкий риск: признаков недостаточно — наблюдение без действий."


def _note(hit: Hit) -> str:
    q = hit.quotes[0] if hit.quotes else None
    base = hit.label
    if hit.note:
        base = f"{base} — {hit.note}"
    if q and q.text and not q.text.startswith("("):
        how = VIEW_LABELS.get(q.view, "")
        where = SOURCE_LABELS.get(q.source, q.source)
        extra = ", ".join(x for x in (where if q.source != "text" else "", how) if x)
        base = f"{base}: «{q.text}»" + (f" ({extra})" if extra else "")
    return base


def _line(factor: str, track: str, weight: int, strength: float, contribution: float,
          note: str, evidence_ids: list[str], *, kind: str = "signal", hit: Hit | None = None) -> dict:
    return {
        "factor": factor, "label": lexicon.label_for(factor) if kind == "signal" else note.split(":")[0],
        "track": track, "kind": kind, "weight": weight, "strength": round(strength, 3),
        "contribution": round(contribution, 2), "evidence_ids": list(evidence_ids), "note": note,
        "detail": hit.note if hit else "",
        "quotes": [q.__dict__ for q in hit.quotes] if hit else [],
    }


def _score_track(track: str, hits: dict[str, Hit], ev: list[str], *, has_license: bool,
                 direct_link: bool = False) -> tuple[int, list[dict]]:
    weights = TRACK_WEIGHTS[track]
    lines: list[dict] = []
    raw = 0.0
    for sid, w in weights.items():
        h = hits.get(sid)
        if not h or h.strength <= 0:
            continue
        c = w * min(1.0, h.strength)
        raw += c
        lines.append(_line(sid, track, w, h.strength, c, _note(h), ev, hit=h))
    if raw <= 0:
        return 0, []

    def has(sid: str) -> bool:
        return sid in hits and hits[sid].strength > 0

    def cap(limit: float, why: str) -> None:
        nonlocal raw
        if raw > limit:
            lines.append(_line(f"gate.{track}", track, 0, 1.0, limit - raw, why, ev, kind="adjustment"))
            raw = limit

    def scale(factor: float, why: str) -> None:
        nonlocal raw
        new = raw * factor
        if new < raw:
            lines.append(_line(f"mitigation.{track}", track, 0, factor, new - raw, why, ev, kind="adjustment"))
            raw = new

    if track == "lottery":
        strong_context = (has("lottery.giveaway") and hits["lottery.giveaway"].strength >= 1.0) \
            or has("lottery.random_draw")
        context = strong_context or has("lottery.giveaway")
        paid = has("lottery.paid_entry") or (has("shared.personal_transfer") and context)
        if not context:
            cap(25, "Ограничение: нет признаков розыгрыша/лотереи — оплата может относиться к другому")
        elif not paid:
            cap(25, "Ограничение: нет признака платного участия — похоже на обычный конкурс")
        elif not strong_context and not has("shared.personal_transfer"):
            # «взнос + призовой фонд» without randomness or private transfers = a tournament
            cap(35, "Ограничение: нет признаков случайного выбора/розыгрыша — похоже на турнир или конкурс мастерства")
        if has("lottery.free_mechanics") and not has("lottery.paid_entry"):
            scale(0.5, "Смягчение: механика бесплатного конкурса (подписка/лайк/отметка друга)")
    elif track == "casino":
        core = has("casino.gambling") or has("casino.brand") or has("visual.gambling")
        promotion = any(has(s) for s in CASINO_PROMOTION)
        if not core:
            if has("casino.native_win") and (has("casino.promo_code") or has("casino.tracking_link")
                                             or has("casino.proxy_channel") or has("casino.call_to_action")):
                cap(50, "Ограничение: игра явно не названа — вывод только по нативной рекламе и ссылке")
            else:
                cap(20, "Ограничение: нет лексики азартных игр или игрового бренда")
        elif not promotion:
            cap(35, "Ограничение: упоминание азартных игр без продвижения (ссылки, промокода, призыва)")
        if has_license:
            scale(0.5, "Смягчение: оператор найден в реестре лицензий — проверить соблюдение правил рекламы")
    elif track == "pyramid":
        core = has("pyramid.unrealistic_return") or has("pyramid.recruitment_income")
        if not core:
            if has("pyramid.referral") and (has("shared.personal_transfer") or has("pyramid.entry_payment")):
                scale(0.8, "Смягчение: нет явного обещания доходности — реферальный сбор денег")
            else:
                cap(30, "Ограничение: нет обещания нереалистичной доходности или дохода от привлечения")

    if has("shared.warning_context") and not direct_link and not any(has(s) for s in DIRECT_CALL):
        scale(0.4, "Смягчение: текст предупреждает о мошенничестве (новость/просвещение), прямого призыва нет")

    cap(100, "Максимум шкалы — 100")
    score = int(round(max(0.0, raw)))
    # rounding remainder keeps Σ contributions == score
    total = sum(l["contribution"] for l in lines)
    if lines and abs(total - score) >= 0.01:
        lines[-1]["contribution"] = round(lines[-1]["contribution"] + (score - total), 2)
    return score, lines


def score_detection(detection: Detection | None = None, *, hits: dict[str, Hit] | None = None,
                    identifiers: dict | None = None,
                    has_license: bool = False, scheme_matches: int = 0, related_objects: int = 0,
                    evidence_ids: list[str] | None = None) -> risk_engine.RiskAssessment:
    """Score a detection (or bare hits) into a RiskAssessment with per-track details."""
    hits = dict(hits if hits is not None else (detection.hits if detection else {}))
    ev = list(evidence_ids or [])
    net = min(1.0, scheme_matches / 5.0 + related_objects / 10.0)
    if net > 0:
        hits["network.links"] = Hit("network.links", "shared", net,
                                    note=f"совпадений со схемами: {scheme_matches}, связанных объектов: {related_objects}")

    ids = identifiers if identifiers is not None else (detection.identifiers if detection else {})
    direct_link = any(ids.get(k) for k in _LINK_IDS)
    per_track: dict[str, tuple[int, list[dict]]] = {}
    for track in lexicon.TRACKS:
        per_track[track] = _score_track(track, hits, ev, has_license=has_license, direct_link=direct_link)
    # network links alone never make a track
    for track, (s, lines) in list(per_track.items()):
        if lines and all(l["factor"] in ("network.links",) or l["kind"] != "signal" for l in lines):
            per_track[track] = (0, [])

    best = max(lexicon.TRACKS, key=lambda t: (per_track[t][0], -lexicon.TRACKS.index(t)))
    score, breakdown = per_track[best]
    level = level_for(score)
    tracks = {t: {"score": s, "threat_level": level_for(s).value, "label": lexicon.TRACK_LABELS[t]}
              for t, (s, _) in per_track.items()}
    if score == 0:
        best = ""
    multi = [t for t, (s, _) in per_track.items() if s >= MEDIUM]

    signals = [
        {**h.to_dict(), "track": h.track}
        for h in hits.values() if h.signal != "network.links"
    ]
    return risk_engine.RiskAssessment(
        score=score, threat_level=level,
        breakdown=sorted(breakdown, key=lambda b: b["contribution"], reverse=True),
        recommendation=recommendation_for(level, best),
        track=best, tracks=tracks, signals=signals,
        multi_track=multi if len(multi) > 1 else [],
        language=detection.language if detection else "",
        disclaimer=DISCLAIMER,
    )


def assessment_dict(a: risk_engine.RiskAssessment) -> dict:
    """JSON shape the API / UI consume (superset of the legacy risk dict)."""
    return {
        "score": a.score,
        "threat_level": a.threat_level.value,
        "level_ru": LEVEL_RU.get(a.threat_level.value, a.threat_level.value),
        "breakdown": a.breakdown,
        "recommendation": a.recommendation,
        "track": a.track,
        "track_label": lexicon.TRACK_LABELS.get(a.track, ""),
        "tracks": a.tracks,
        "signals": a.signals,
        "multi_track": a.multi_track,
        "language": a.language,
        "disclaimer": a.disclaimer or DISCLAIMER,
    }
