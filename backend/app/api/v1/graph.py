"""Fraud Graph endpoints — subgraph, GDS insights, scheme rebuild."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session

router = APIRouter()
_audit = logging.getLogger("afm.audit")


class SamePersonBody(BaseModel):
    account_a: str
    account_b: str


@router.post("/same-person")
async def confirm_same_person(
    body: SamePersonBody,
    principal: Principal = Depends(require_role(Role.SUPERVISOR)),
    session: Session = Depends(get_session),
) -> dict:
    """Analyst confirms a SAME_PERSON candidate -> writes a confirmed edge (audited)."""
    from app.db.clients import neo4j_driver
    from app.services.graph_builder import GraphBuilder

    record_action(session, principal.subject, "same_person.confirm",
                  f"{body.account_a}~{body.account_b}")
    GraphBuilder(neo4j_driver()).confirm_same_person(
        body.account_a, body.account_b, principal.subject
    )
    return {"confirmed": True, "by": principal.subject}


@router.post("/schemas/rebuild")
async def rebuild_schemas(
    principal: Principal = Depends(require_role(Role.SUPERVISOR)),
    session: Session = Depends(get_session),
) -> dict:
    """Cluster all fingerprints (Qdrant) into ScamSchema nodes (Neo4j). Heavier op."""
    from app.db.clients import neo4j_driver, qdrant_client
    from app.services.clustering import rebuild_scam_schemas
    from app.services.fingerprint import FingerprintStore
    from app.services.graph_builder import GraphBuilder

    record_action(session, principal.subject, "schema.rebuild", "-")
    schemas = rebuild_scam_schemas(
        FingerprintStore(qdrant_client()), GraphBuilder(neo4j_driver())
    )
    return {"schemas": schemas, "count": len(schemas)}


@router.get("/insights")
async def graph_insights(
    principal: Principal = Depends(require_role(Role.ANALYST)),
) -> dict:
    """GDS analytics: communities (organized networks) + ringleaders (centrality)."""
    from app.db.clients import neo4j_driver
    from app.services.graph_builder import GraphBuilder

    _audit.info("graph.insights actor=%s", principal.subject)
    gb = GraphBuilder(neo4j_driver())
    return {"communities": gb.detect_communities(), "ringleaders": gb.ringleader_candidates()}


@router.get("/money-flow/{account}")
async def money_flow(
    account: str,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Public on-chain flow: account → wallet → exchange. Stops at the exchange
    boundary (wallet → bank account is enriched by the agency's data, not ours)."""
    from app.core.config import settings
    from app.db.clients import neo4j_driver
    from app.services.chain import get_onchain_client
    from app.services.graph_builder import GraphBuilder
    from app.services.money_flow import KNOWN_EXCHANGES, build_flow

    record_action(session, principal.subject, "money_flow.view", account)
    wallets = GraphBuilder(neo4j_driver()).wallets_for(account)
    client = get_onchain_client()
    edges: list[dict] = []
    for w in wallets:
        try:
            edges += [{"from": w, "to": c["to"]}
                      for c in client.counterparties(w, limit=settings.onchain_counterparty_limit)]
        except Exception:  # noqa: BLE001 — on-chain best-effort
            pass
    return build_flow(account, wallets, edges, KNOWN_EXCHANGES)


@router.get("/accounts")
async def graph_accounts(
    principal: Principal = Depends(require_role(Role.ANALYST)),
) -> list[str]:
    """Accounts that actually exist in the Fraud Graph (have ≥1 edge) — the only
    ones worth offering in the graph picker. Declared before /{seed} so the literal
    path wins over the parameter route."""
    from app.db.clients import neo4j_driver
    from app.services.graph_builder import GraphBuilder

    return GraphBuilder(neo4j_driver()).connected_accounts()


@router.get("/{seed}")
async def get_graph(
    seed: str,
    principal: Principal = Depends(require_role(Role.ANALYST)),
) -> dict:
    from app.db.clients import neo4j_driver
    from app.services.graph_builder import GraphBuilder

    _audit.info("graph.view actor=%s seed=%s", principal.subject, seed)
    return GraphBuilder(neo4j_driver()).subgraph(seed)
