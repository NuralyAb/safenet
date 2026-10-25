"""AI Investigator activities — the side-effecting steps of the investigation.

Each maps to a ТЗ step:
  collect_profile     -> Шаг 1: собрать последние видео, контакты, ссылки
  match_fingerprints  -> Шаг 2: поиск похожих схем в Scam Fingerprint DB (Qdrant)
  build_network       -> Шаг 3: построение графа связей (Neo4j)
  compute_risk        -> детерминированный Risk Engine (LLM не ставит балл!)
  compose_report      -> Шаг 4: LLM формулирует отчёт ПО ФАКТАМ

Activities can do I/O and are retried by Temporal. The risk SCORE is computed
deterministically; the LLM only writes the human-readable narrative.
"""
from __future__ import annotations

from temporalio import activity

from app.services import risk_engine
from app.workflows.types import (
    InvestigationInput,
    NetworkSummary,
    ProfileData,
    RiskResult,
    SchemeMatch,
)


@activity.defn
async def collect_profile(req: InvestigationInput) -> ProfileData:
    """Read the target's content from Postgres -> profile."""
    from app.db.models import Content
    from app.db.session import get_session
    from app.services.investigation import profile_from_content

    gen = get_session()
    session = next(gen)
    try:
        rows = session.query(Content).filter_by(author=req.target).all()
        return profile_from_content(rows, req.target)
    finally:
        gen.close()


@activity.defn
async def match_fingerprints(profile: ProfileData) -> list[SchemeMatch]:
    """Accounts sharing a hard identifier (wallet/telegram) with the target = repeating scheme."""
    from app.db.clients import neo4j_driver
    from app.services.graph_builder import GraphBuilder

    return GraphBuilder(neo4j_driver()).shared_identifier_accounts(profile.target)


@activity.defn
async def build_network(profile: ProfileData) -> NetworkSummary:
    """Count related objects 1-2 hops out in the Fraud Graph."""
    from app.db.clients import neo4j_driver
    from app.services.graph_builder import GraphBuilder

    return GraphBuilder(neo4j_driver()).network_summary(profile.target)


@activity.defn
async def compute_risk(
    profile: ProfileData,
    matches: list[SchemeMatch],
    network: NetworkSummary,
) -> RiskResult:
    """Map established facts -> FactorSignals -> deterministic score. Fully traceable."""
    from app.services.investigation import risk_signals

    a = risk_engine.assess(risk_signals(profile, matches, network))
    return RiskResult(
        score=a.score,
        threat_level=a.threat_level.value,
        breakdown=a.breakdown,
        recommendation=a.recommendation,
    )


@activity.defn
async def persist_assessment(target: str, risk: RiskResult) -> None:
    """Save the assessment so it appears in the triage queue (upsert by target)."""
    from app.db.risk_repo import upsert_assessment
    from app.db.session import get_session

    gen = get_session()
    session = next(gen)
    try:
        upsert_assessment(session, target, risk.score, risk.threat_level,
                          risk.breakdown, risk.recommendation)
    finally:
        gen.close()


@activity.defn
async def compose_narrative(
    profile: ProfileData, risk: RiskResult, matches_count: int, network: NetworkSummary
) -> str:
    """LLM writes the narrative FROM the established facts. Never scores; falls back on failure."""
    from app.services.ai.factory import get_llm
    from app.services.investigation import compose_narrative_text

    return compose_narrative_text(get_llm(), profile, risk, matches_count, network)
