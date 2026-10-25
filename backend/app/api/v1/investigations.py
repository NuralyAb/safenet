"""Investigation endpoints.

POST /investigations launches the AI Investigator (a durable Temporal workflow)
for a target handle and returns a workflow id. The dashboard polls GET to fetch
status and, when finished, the evidence-backed report.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role, settings
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session
from app.workflows.types import InvestigationInput  # plain dataclass, no temporalio import

router = APIRouter()


class InvestigationRequest(BaseModel):
    target: str            # e.g. "@money_fast"
    requested_by: str      # analyst id — recorded in the audit log


class InvestigationCreated(BaseModel):
    workflow_id: str
    target: str
    status: str = "RUNNING"


class Links(BaseModel):
    accounts: int = 0
    sites: int = 0
    wallets: int = 0


class Report(BaseModel):
    """Dashboard-facing report (matches frontend `Report` in api/client.ts)."""
    target: str
    category: str
    risk_score: int
    threat_level: str
    findings: list[str]
    links: Links


class InvestigationStatus(BaseModel):
    workflow_id: str
    status: str
    report: Report | None = None


def _to_report(raw: Any) -> Report:
    """Map the internal workflow result (nested risk/network) to the flat dashboard shape.

    Temporal decodes the result to a dict when the handle is untyped, so read defensively.
    """
    risk = raw.get("risk", {}) if isinstance(raw, dict) else {}
    net = raw.get("network", {}) if isinstance(raw, dict) else {}
    return Report(
        target=raw.get("target", ""),
        category=raw.get("category", ""),
        risk_score=int(risk.get("score", 0)),
        threat_level=risk.get("threat_level", "LOW"),
        findings=raw.get("findings", []),
        links=Links(
            accounts=net.get("accounts", 0),
            sites=net.get("websites", 0),
            wallets=net.get("wallets", 0),
        ),
    )


def _workflow_id(target: str) -> str:
    return f"inv-{target.lstrip('@')}"


async def _temporal_client():
    from temporalio.client import Client

    try:
        return await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )
    except Exception as exc:  # noqa: BLE001 — surface as 503 to the dashboard
        raise HTTPException(status_code=503, detail=f"Temporal unavailable: {exc}") from exc


@router.post("", response_model=InvestigationCreated)
async def open_investigation(
    req: InvestigationRequest,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> InvestigationCreated:
    import uuid

    from app.workflows.investigator import AIInvestigatorWorkflow  # lazy: avoid temporalio at import

    client = await _temporal_client()
    # Unique per run so re-investigating the same account never collides.
    wf_id = f"{_workflow_id(req.target)}-{uuid.uuid4().hex[:8]}"
    # Audit who/what/when before starting — tamper-evident, append-only.
    record_action(session, principal.subject, "investigation.open", req.target)
    await client.start_workflow(
        AIInvestigatorWorkflow.run,
        InvestigationInput(target=req.target, requested_by=req.requested_by),
        id=wf_id,
        task_queue=settings.temporal_task_queue,
    )
    return InvestigationCreated(workflow_id=wf_id, target=req.target)


@router.get("/{workflow_id}", response_model=InvestigationStatus)
async def get_investigation(
    workflow_id: str,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> InvestigationStatus:
    record_action(session, principal.subject, "investigation.view", workflow_id)
    client = await _temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()
    status = desc.status.name if desc.status else "UNKNOWN"

    report = None
    if status == "COMPLETED":
        report = _to_report(await handle.result())
    return InvestigationStatus(workflow_id=workflow_id, status=status, report=report)


@router.get("/{workflow_id}/evidence-package")
async def evidence_package(
    workflow_id: str,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Generate the «Аналитическая справка» — AI output bound to chain of custody."""
    from datetime import datetime, timezone

    from app.db.models import Content, Evidence
    from app.services.evidence_package import build_package, render_markdown

    client = await _temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()
    if not desc.status or desc.status.name != "COMPLETED":
        raise HTTPException(status_code=409, detail="Investigation not completed yet")

    raw = await handle.result()
    target = raw.get("target", "") if isinstance(raw, dict) else ""
    rows = (
        session.query(Evidence, Content)
        .join(Content, Evidence.content_id == Content.id)
        .filter(Content.author == target)
        .all()
    )
    evidence = [
        {"sha256": e.sha256, "evidence_key": e.evidence_key,
         "collected_at": c.collected_at.isoformat() if c.collected_at else None,
         "source": c.source, "url": c.url}
        for e, c in rows
    ]
    record_action(session, principal.subject, "evidence_package.generate", target)
    package = build_package(
        raw, evidence,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generated_by=principal.subject,
    )
    return {"package": package, "markdown": render_markdown(package)}
