"""AI Investigator — durable, replayable, auditable investigation workflow.

Why Temporal: a law-enforcement investigation must be reproducible. Temporal
records every step and its result, so the whole investigation can be replayed
deterministically and folded into the evidence chain.

The workflow only orchestrates; all I/O lives in activities. Retries/timeouts
are declared per activity.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        build_network,
        collect_profile,
        compose_narrative,
        compute_risk,
        match_fingerprints,
        persist_assessment,
    )
    from app.workflows.types import InvestigationInput, InvestigationReport

_RETRY = RetryPolicy(maximum_attempts=3)
_SHORT = timedelta(seconds=30)
_LONG = timedelta(minutes=5)   # collection / inference can be slow


@workflow.defn
class AIInvestigatorWorkflow:
    @workflow.run
    async def run(self, req: InvestigationInput) -> InvestigationReport:
        # Шаг 1 — собрать профиль
        profile = await workflow.execute_activity(
            collect_profile, req, start_to_close_timeout=_LONG, retry_policy=_RETRY
        )
        # Шаг 2 — поиск повторяющихся схем
        matches = await workflow.execute_activity(
            match_fingerprints, profile, start_to_close_timeout=_LONG, retry_policy=_RETRY
        )
        # Шаг 3 — построить граф связей
        network = await workflow.execute_activity(
            build_network, profile, start_to_close_timeout=_LONG, retry_policy=_RETRY
        )
        # Детерминированная оценка риска
        risk = await workflow.execute_activity(
            compute_risk, args=[profile, matches, network],
            start_to_close_timeout=_SHORT, retry_policy=_RETRY,
        )
        # Persist for the triage queue (sorted by risk for analyst review)
        await workflow.execute_activity(
            persist_assessment, args=[req.target, risk],
            start_to_close_timeout=_SHORT, retry_policy=_RETRY,
        )
        # Шаг 4 — отчёт (LLM формулирует по фактам)
        narrative = await workflow.execute_activity(
            compose_narrative, args=[profile, risk, len(matches), network],
            start_to_close_timeout=_LONG, retry_policy=_RETRY,
        )

        category = "Investment Fraud" if profile.promises_returns else "Suspicious Activity"
        return InvestigationReport(
            target=req.target,
            category=category,
            risk=risk,
            findings=[b["note"] for b in risk.breakdown if b.get("note")],
            scheme_matches=len(matches),
            network=network,
            narrative=narrative,
        )
