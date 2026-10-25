"""Accounts known to the system — for the investigation picker (no mock data)."""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.models import Content, ContentRisk, RiskAssessment
from app.db.session import get_session
from app.services.extract import extract_identifiers

router = APIRouter()


@router.get("", response_model=list[str])
def list_accounts(
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> list[str]:
    """Distinct accounts that actually have data (collected content or an assessment)."""
    authors = {a for (a,) in session.query(Content.author).distinct() if a}
    targets = {t for (t,) in session.query(RiskAssessment.target).distinct() if t}
    return sorted(authors | targets)


class CollectIn(BaseModel):
    account: str
    source: str = ""        # auto-detected from stored content if empty
    limit: int | None = None  # max videos to download (defaults to COLLECT_VIDEO_LIMIT)


@router.post("/collect")
def collect_account(
    body: CollectIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Collect this account's other videos (background) so the investigation gets
    a fuller picture — more wallets/links/network. Runs the full pipeline per video."""
    from app.workers.tasks import ingest

    source = body.source
    if not source:
        row = session.query(Content.source).filter_by(author=body.account).first()
        source = (row[0] if row and row[0] else "youtube")

    limit = body.limit if (body.limit and body.limit > 0) else None
    record_action(session, principal.subject, "account.collect", f"{source}:{body.account}:{limit or 'default'}")
    ingest(source, body.account, kind="account", limit=limit)
    return {"started": True, "account": body.account, "source": source,
            "limit": limit or "default"}


class DiscoverIn(BaseModel):
    query: str             # keyword / hashtag (e.g. «инвест казино без лицензии»)
    source: str = "youtube"
    limit: int | None = None


@router.post("/discover")
def discover_accounts(
    body: DiscoverIn,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Scam Radar — proactively DISCOVER new suspicious content by keyword/hashtag
    (not a known @handle). Runs the full pipeline per found item; results land in the
    materials queue / accounts. Offline-safe under AI_PROVIDER=mock."""
    from app.workers.tasks import ingest

    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    limit = body.limit if (body.limit and body.limit > 0) else None
    record_action(session, principal.subject, "account.discover", f"{body.source}:{query}:{limit or 'default'}")
    ingest(body.source, query, kind="keyword", limit=limit)
    return {"started": True, "query": query, "source": body.source, "limit": limit or "default"}


# --- Target dossier: one-screen portrait of everything known about an account ----
class DossierVideo(BaseModel):
    content_id: str
    url: str
    source: str
    score: int | None
    threat_level: str | None
    priority: int
    disposition: str
    reach: dict
    identifiers: dict           # {telegram, wallets, phones, domains} for THIS video
    caption: str = ""           # original post text
    transcript: str
    ocr_text: str
    tags: list


class DossierIdentifier(BaseModel):
    kind: str                   # telegram | wallet | phone | domain
    value: str
    count: int                  # in how many of this account's videos it appears
    videos: list[str]           # content_ids where it appears


def _signal_label(factor: str) -> str:
    from app.services.safenet.lexicon import label_for
    return label_for(factor)


class DossierPattern(BaseModel):
    factor: str
    label: str = ""             # human-readable SafeNet signal name
    videos: int                 # how many videos exhibit this risk factor
    avg_contribution: float


class LinkedAccount(BaseModel):
    author: str
    shared: list[str]           # shared hard identifiers (the «same scheme» signal)


class Dossier(BaseModel):
    account: str
    source: str
    overall: dict | None        # account-level RiskAssessment roll-up
    totals: dict                # videos / scored / avg_score / max_score / total_views
    videos: list[DossierVideo]
    identifiers: list[DossierIdentifier]
    pattern: list[DossierPattern]
    linked_accounts: list[LinkedAccount]
    whois: list[dict]           # RDAP enrichment for the domains the account advertises
    campaign: dict              # «от видео к сети» rollup: posts → accounts → priority


def _video_text(c: Content | None) -> str:
    if c is None:
        return ""
    return " ".join(filter(None, [c.caption, c.transcript, c.ocr_text]))


@router.get("/{account:path}/dossier", response_model=Dossier)
def account_dossier(
    account: str,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> Dossier:
    """Full portrait of one target: its videos + per-video risk, the aggregated
    hard identifiers it advertises (Telegram channels / wallets / phones / domains),
    the recurring risk pattern, and other accounts sharing those identifiers."""
    record_action(session, principal.subject, "account.dossier", account)

    contents = {c.id: c for c in session.query(Content).filter_by(author=account).all()}
    risks = {r.content_id: r for r in session.query(ContentRisk).filter_by(author=account).all()}
    assessment = session.query(RiskAssessment).filter_by(target=account).one_or_none()

    source = ""
    for c in contents.values():
        if c.source:
            source = c.source
            break
    if not source and risks:
        source = next((r.source for r in risks.values() if r.source), "")

    # Aggregators across the account's videos.
    agg: dict[tuple[str, str], set[str]] = defaultdict(set)   # (kind, value) -> {content_id}
    factor_count: dict[str, int] = defaultdict(int)
    factor_sum: dict[str, float] = defaultdict(float)

    videos: list[DossierVideo] = []
    for cid in sorted(set(contents) | set(risks),
                      key=lambda x: risks[x].priority if x in risks else 0, reverse=True):
        c = contents.get(cid)
        r = risks.get(cid)
        ids = extract_identifiers(_video_text(c))
        for kind, key in (("telegram", "telegram"), ("wallet", "wallets"),
                          ("phone", "phones"), ("domain", "domains")):
            for v in ids.get(key, []):
                agg[(kind, v)].add(cid)
        if r:
            for f in (r.breakdown or []):
                contrib = float(f.get("contribution", 0) or 0)
                if contrib > 0:
                    factor_count[f.get("factor", "")] += 1
                    factor_sum[f.get("factor", "")] += contrib
        videos.append(DossierVideo(
            content_id=cid,
            url=(c.url if c else (r.url if r else "")) or "",
            source=(c.source if c else (r.source if r else "")) or "",
            score=r.score if r else None,
            threat_level=r.threat_level if r else None,
            priority=r.priority if r else 0,
            disposition=r.disposition if r else "pending",
            reach={"views": r.views, "likes": r.likes, "comments": r.comments,
                   "shares": r.shares} if r else {},
            identifiers=ids,
            caption=(c.caption if c else "") or "",
            transcript=(c.transcript if c else "") or "",
            ocr_text=(c.ocr_text if c else "") or "",
            tags=(c.tags if c and c.tags else []),
        ))

    identifiers = sorted(
        (DossierIdentifier(kind=k, value=v, count=len(cids), videos=sorted(cids))
         for (k, v), cids in agg.items()),
        key=lambda d: (-d.count, d.kind, d.value),
    )
    pattern = sorted(
        (DossierPattern(factor=f, label=_signal_label(f), videos=n, avg_contribution=round(factor_sum[f] / n, 1))
         for f, n in factor_count.items()),
        key=lambda p: (-p.videos, -p.avg_contribution),
    )

    # WHOIS/RDAP enrichment for advertised domains — best-effort OSINT on the target.
    whois: list[dict] = []
    from app.services.whois import lookup_domain
    for ident in identifiers:
        if ident.kind == "domain":
            info = lookup_domain(ident.value)
            if info:
                whois.append(info)

    # Linked accounts (shared hard identifiers) — best-effort: the graph may be down.
    linked: list[LinkedAccount] = []
    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import GraphBuilder

        for m in GraphBuilder(neo4j_driver()).shared_identifier_accounts(account):
            linked.append(LinkedAccount(author=m.author, shared=list(m.shared_identifiers)))
    except Exception:  # noqa: BLE001 — graph is an enrichment, not a hard dependency
        pass

    scored = [r.score for r in risks.values()]
    totals = {
        "videos": len(set(contents) | set(risks)),
        "scored": len(scored),
        "avg_score": round(sum(scored) / len(scored)) if scored else None,
        "max_score": max(scored) if scored else None,
        "total_views": sum(r.views for r in risks.values()),
    }
    overall = None
    if assessment:
        overall = {
            "score": assessment.score, "threat_level": assessment.threat_level,
            "breakdown": assessment.breakdown, "recommendation": assessment.recommendation,
            "disposition": assessment.disposition,
        }

    campaign = _campaign_rollup(session, account, linked, identifiers, totals, overall)

    return Dossier(account=account, source=source, overall=overall, totals=totals,
                   videos=videos, identifiers=identifiers, pattern=pattern,
                   linked_accounts=linked, whois=whois, campaign=campaign)


def _threat_label(score: int | None) -> str:
    if score is None:
        return "LOW"
    return ("CRITICAL" if score >= 85 else "HIGH" if score >= 65
            else "MEDIUM" if score >= 40 else "LOW")


def _campaign_rollup(session, account, linked, identifiers, totals, overall) -> dict:
    """«От видео — к сети»: свернуть аккаунт + связанные в одну кампанию с приоритетом.

    Cheap (DB + already-computed links, no GDS): network = seed ∪ linked accounts;
    posts across the network; shared identifiers; ringleader = the most-connected
    account; priority = the max risk across the network.
    """
    network = [account] + [l.author for l in linked]
    posts = session.query(Content).filter(Content.author.in_(network)).count()
    net_scores = [r.score for r in
                  session.query(RiskAssessment).filter(RiskAssessment.target.in_(network)).all()]
    own = (overall or {}).get("score")
    max_risk = max([s for s in [*net_scores, own, totals.get("max_score")] if s is not None],
                   default=0)
    # Ringleader heuristic (no GDS): account sharing the most hard identifiers.
    ringleader = account
    if linked:
        top = max(linked, key=lambda l: len(l.shared))
        if len(top.shared) >= max((len(l.shared) for l in linked), default=0):
            ringleader = top.author if len(top.shared) > 0 else account
    return {
        "posts": posts,
        "accounts": len(network),
        "wallets": sum(1 for i in identifiers if i.kind == "wallet"),
        "telegram": sum(1 for i in identifiers if i.kind == "telegram"),
        "domains": sum(1 for i in identifiers if i.kind == "domain"),
        "phones": sum(1 for i in identifiers if i.kind == "phone"),
        "shared_identifiers": sorted({s for l in linked for s in l.shared}),
        "ringleader": ringleader,
        "max_risk": max_risk,
        "threat_level": _threat_label(max_risk),
        "is_network": len(network) > 1,
    }
