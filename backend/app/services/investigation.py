"""Investigation logic — pure functions the Temporal activities delegate to.

Kept free of temporalio and live-DB imports so it unit-tests cleanly. Activities
fetch rows / call stores, then hand the raw results to these mappers.
"""
from __future__ import annotations

import json

from app.services import risk_engine
from app.workflows.types import NetworkSummary, ProfileData, RiskResult, SchemeMatch


def profile_from_content(rows, target: str) -> ProfileData:
    """Build a profile from the target's Content rows, aggregating NLP claim flags."""
    from app.services.claims import CLAIM_KEYS, aggregate_claims

    claims = aggregate_claims([
        {k: getattr(r, k, False) for k in CLAIM_KEYS} for r in rows
    ])
    return ProfileData(
        target=target,
        content_ids=[r.id for r in rows],
        promises_returns=claims["promises_returns"],
        has_referral=claims["has_referral"],
        has_license=claims["has_license"],
        gambling_content=claims["gambling_content"],
    )


def scheme_matches_from_rows(rows: list[dict]) -> list[SchemeMatch]:
    """Map graph rows (accounts sharing a hard identifier) to SchemeMatch."""
    return [
        SchemeMatch(
            content_id=r["author"],
            author=r["author"],
            score=float(r.get("score", 1.0)),
            shared_identifiers=list(r.get("shared", [])),
        )
        for r in rows
    ]


def network_summary_from_row(row: dict) -> NetworkSummary:
    return NetworkSummary(
        related_objects=int(row.get("related", 0)),
        accounts=int(row.get("accounts", 0)),
        telegram_channels=int(row.get("telegram", 0)),
        wallets=int(row.get("wallets", 0)),
        websites=int(row.get("websites", 0)),
        community_id=row.get("community"),
    )


def _node_type(node_id: str, labels) -> str:
    labels = set(labels or [])
    if "Account" in labels:
        return "account"
    if "Person" in labels:
        return "person"
    if node_id.startswith("wallet:"):
        return "wallet"
    return "infrastructure"


def subgraph_from_edge_rows(rows: list[dict]) -> dict:
    """Map Neo4j relationship rows -> {nodes, edges} for the dashboard graph.

    Unconfirmed SAME_PERSON links are surfaced as 'SAME_PERSON?' so the frontend
    renders them as dashed candidate edges (analyst confirms before they're fact).
    """
    nodes: dict[str, str] = {}
    edges: list[dict] = []
    for r in rows:
        s, t = r["source"], r["target"]
        nodes.setdefault(s, _node_type(s, r.get("source_labels")))
        nodes.setdefault(t, _node_type(t, r.get("target_labels")))
        label = r["label"]
        if label == "SAME_PERSON" and r.get("confirmed") is False:
            label = "SAME_PERSON?"
        edges.append({
            "source": s, "target": t, "label": label,
            "confidence": r.get("confidence"), "evidence_id": r.get("evidence_id"),
        })
    return {
        "nodes": [{"id": nid, "type": ntype} for nid, ntype in nodes.items()],
        "edges": edges,
    }


# --- AI Investigator narrative ----------------------------------------------
# The LLM writes prose FROM established facts. It must never assign the risk
# score — that comes from the deterministic Risk Engine (invariant).
_NARRATIVE_SYSTEM = (
    "Ты — аналитик по финансовому мошенничеству. Сформулируй краткий отчёт (3-5 предложений) "
    "СТРОГО по предоставленным фактам. Не добавляй ничего, чего нет в фактах, и НЕ оценивай "
    "риск числом — балл уже посчитан системой и указан в фактах. Пиши по-русски."
)


def _facts(profile: ProfileData, risk: RiskResult, matches_count: int,
           network: NetworkSummary) -> dict:
    return {
        "target": profile.target,
        "risk_score": risk.score,
        "threat_level": risk.threat_level,
        "findings": [b["note"] for b in risk.breakdown if b.get("note")],
        "scheme_matches": matches_count,
        "network": {
            "related_objects": network.related_objects,
            "accounts": network.accounts,
            "wallets": network.wallets,
        },
        "recommendation": risk.recommendation,
    }


def narrative_prompt(profile: ProfileData, risk: RiskResult, matches_count: int,
                     network: NetworkSummary) -> tuple[str, str]:
    user = "Факты:\n" + json.dumps(_facts(profile, risk, matches_count, network), ensure_ascii=False)
    return _NARRATIVE_SYSTEM, user


def fallback_narrative(profile: ProfileData, risk: RiskResult, matches_count: int,
                       network: NetworkSummary) -> str:
    """Deterministic template used when the LLM is unavailable."""
    lines = [f"Объект {profile.target}: risk {risk.score}/100 ({risk.threat_level})."]
    for note in (b["note"] for b in risk.breakdown if b.get("note")):
        lines.append(f"Признак: {note}.")
    if matches_count:
        lines.append(f"Повтор схемы: {matches_count} связанных аккаунтов.")
    lines.append(
        f"Сеть: {network.related_objects} объектов "
        f"({network.accounts} аккаунтов, {network.wallets} кошельков)."
    )
    lines.append(f"Рекомендация: {risk.recommendation}.")
    return " ".join(lines)


def compose_narrative_text(llm, profile: ProfileData, risk: RiskResult,
                           matches_count: int, network: NetworkSummary) -> str:
    """Call the LLM with facts; fall back to the template on any failure."""
    system, user = narrative_prompt(profile, risk, matches_count, network)
    try:
        text = (llm.complete(system, user) or "").strip()
        return text or fallback_narrative(profile, risk, matches_count, network)
    except Exception:  # noqa: BLE001 — never let narrative generation break an investigation
        return fallback_narrative(profile, risk, matches_count, network)


def risk_signals(profile: ProfileData, matches: list[SchemeMatch],
                 network: NetworkSummary) -> list[risk_engine.FactorSignal]:
    """Map established facts to the 6 weighted factors (LLM never scores)."""
    F = risk_engine.FactorSignal
    return [
        F("financial_promises", 1.0 if profile.promises_returns else 0.0,
          note="обещание гарантированной прибыли" if profile.promises_returns else ""),
        F("referral_structure", 1.0 if profile.has_referral else 0.0,
          note="реферальная система" if profile.has_referral else ""),
        F("known_scheme_repetition", min(1.0, len(matches) / 10.0),
          note=f"совпадений со схемами: {len(matches)}"),
        F("suspicious_links", min(1.0, network.related_objects / 30.0),
          note=f"связанных объектов: {network.related_objects}"),
        F("gambling_content", 1.0 if profile.gambling_content else 0.0),
        F("infra_anonymity", 0.0 if profile.has_license else 1.0,
          note="отсутствие лицензии" if not profile.has_license else ""),
    ]


def content_risk_signals(facts: dict, *, scheme_matches: int = 0, related_objects: int = 0,
                         evidence_ids: list[str] | None = None,
                         has_license: bool | None = None) -> list[risk_engine.FactorSignal]:
    """Per-VIDEO factor signals (graded). Same 6 ТЗ factors / weights — but the two
    intensifier signals raise the STRENGTH of their parent factor instead of adding
    a 7th/8th factor (keeps the deterministic weight contract intact, ADR-0003):

      financial_promises  0.0 / 0.6 (обещание) / 1.0 (+агрессивный призыв)
      referral_structure  0.0 / 0.6 (реферал)   / 1.0 (+скрытое вовлечение)

    `evidence_ids` should point to this content's own evidence so every per-video
    point is traceable. `has_license` overrides the text flag (registry-verified).
    """
    F = risk_engine.FactorSignal
    ev = list(evidence_ids or [])
    promises = bool(facts.get("promises_returns"))
    aggressive = bool(facts.get("aggressive_investment"))
    referral = bool(facts.get("has_referral"))
    hidden = bool(facts.get("hidden_engagement"))
    gambling = bool(facts.get("gambling_content"))
    licensed = bool(facts.get("has_license")) if has_license is None else bool(has_license)

    fin_strength = (1.0 if aggressive else 0.6) if promises else 0.0
    ref_strength = (1.0 if hidden else 0.6) if referral else 0.0
    fin_note = ("агрессивный призыв к срочным вложениям" if aggressive
                else "обещание дохода") if promises else ""
    ref_note = ("скрытое вовлечение аудитории" if hidden
                else "реферальная схема") if referral else ""

    return [
        F("financial_promises", fin_strength, list(ev), fin_note),
        F("referral_structure", ref_strength, list(ev), ref_note),
        F("known_scheme_repetition", min(1.0, scheme_matches / 10.0), list(ev),
          f"совпадений со схемами: {scheme_matches}" if scheme_matches else ""),
        F("suspicious_links", min(1.0, related_objects / 30.0), list(ev),
          f"подозрительных объектов: {related_objects}" if related_objects else ""),
        F("gambling_content", 1.0 if gambling else 0.0, list(ev),
          "реклама азартных игр / казино" if gambling else ""),
        F("infra_anonymity", 0.0 if licensed else 1.0, list(ev),
          "отсутствие лицензии" if not licensed else ""),
    ]
