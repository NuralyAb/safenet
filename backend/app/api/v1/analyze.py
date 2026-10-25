"""Ad-hoc analysis — analyze a single video by URL or uploaded file."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Role
from app.core.security import Principal, require_role
from app.db.audit_repo import record_action
from app.db.session import get_session

router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024   # 200 MB cap for ad-hoc uploads


def _persist_content(session, result: dict, source: str, url: str) -> None:
    """Persist the analysed clip as a Content row so its account becomes
    real & investigatable (appears in /accounts and feeds /investigations)."""
    from app.db.models import Content

    claims = result.get("claims", {})
    cid = result["sha256"]
    row = session.get(Content, cid)
    if row is None:
        row = Content(id=cid, external_id=cid, sha256=cid)
        session.add(row)
    row.source = source
    row.author = result.get("author") or "(не указан)"
    row.url = url
    row.lang = result.get("language") or "ru"
    row.caption = result.get("caption") or row.caption
    row.transcript = result.get("transcript") or row.transcript
    row.ocr_text = result.get("ocr_text") or row.ocr_text
    row.tags = result.get("tags") or row.tags
    row.promises_returns = bool(claims.get("promises_returns"))
    row.has_referral = bool(claims.get("has_referral"))
    row.has_license = bool(claims.get("has_license"))
    row.gambling_content = bool(claims.get("gambling_content"))

    # Chain-of-custody row linking this content to its WORM evidence object.
    ev_key = result.get("evidence_key")
    if ev_key:
        from app.db.evidence_repo import upsert_evidence
        upsert_evidence(session, cid, cid, ev_key,
                        int(result.get("size", 0) or 0), result.get("content_type", ""))
    session.commit()


def _persist_content_risk(session, result: dict, source: str, url: str) -> None:
    """Surface the analysed clip in the «Материалы» triage, ranked by risk × reach."""
    from app.db.risk_repo import upsert_content_risk

    risk = result.get("risk", {})
    row = upsert_content_risk(
        session, result["sha256"], risk.get("score", 0), risk.get("threat_level", "LOW"),
        risk.get("breakdown", []), risk.get("recommendation", ""),
        author=result.get("author", ""), source=source, url=url,
        reach=result.get("reach", {}), track=risk.get("track", ""), lang=risk.get("language", ""),
    )
    result["content_risk_id"] = row.id


class AnalyzeUrl(BaseModel):
    url: str
    caption: str = ""


@router.post("/url")
def analyze_url(
    body: AnalyzeUrl,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Download a video (or TikTok photo post) by URL and run the full pipeline."""
    from app.services.adhoc import DownloadFailed, fetch_media, run_analysis
    from app.services.ssrf import UnsafeURLError, check_url

    try:
        check_url(body.url, [], require_allowlist=False)   # block private/metadata, allow public
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_action(session, principal.subject, "analyze.url", body.url)
    try:
        payload = fetch_media(body.url)
    except DownloadFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    source = payload["source"]
    result = run_analysis(payload.get("media"), source=source, url=body.url,
                          caption=payload["caption"] or body.caption,
                          author=payload["author"], images=payload["images"],
                          reach=payload.get("reach"))
    _persist_content(session, result, source, body.url)
    _persist_content_risk(session, result, source, body.url)
    return result


@router.post("/file")
def analyze_file(
    file: UploadFile = File(...),
    caption: str = Form(""),
    author: str = Form(""),
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Analyze an uploaded video OR screenshot/image (text in images: OCR + visual tags)."""
    from app.services.adhoc import run_analysis

    media = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(media) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 200 MB)")
    if not media:
        raise HTTPException(status_code=400, detail="Empty file")

    record_action(session, principal.subject, "analyze.file", file.filename or "upload")
    ctype = (file.content_type or "").lower()
    is_image = ctype.startswith("image/") or (file.filename or "").lower().endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))
    source = "screenshot" if is_image else "upload"
    if is_image:     # screenshot: straight to multi-frame OCR + vision, no ffmpeg
        result = run_analysis(None, source=source, url="", caption=caption, author=author, images=[media])
    else:
        result = run_analysis(media, source=source, url="", caption=caption, author=author)
    _persist_content(session, result, source, "")
    _persist_content_risk(session, result, source, "")
    return result


class AnalyzeText(BaseModel):
    text: str
    kind: str = "post"          # post | stream | chat | ocr
    author: str = ""
    source: str = "text"        # instagram | tiktok | telegram | whatsapp | text …
    url: str = ""


MAX_TEXT = 50_000


@router.post("/text")
def analyze_text(
    body: AnalyzeText,
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Analyse a post / stream transcript / chat message given as text (RU / KZ / translit)."""
    from app.services.adhoc import run_text_analysis

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст")
    if len(text) > MAX_TEXT:
        raise HTTPException(status_code=413, detail="Текст слишком длинный (макс. 50 000 символов)")
    kind = body.kind if body.kind in ("post", "stream", "chat", "ocr") else "post"
    source = (body.source or "text")[:32]
    record_action(session, principal.subject, "analyze.text", f"{kind}:{len(text)}")
    result = run_text_analysis(text, kind=kind, author=body.author.strip()[:200], source=source,
                               url=body.url.strip()[:2000])
    _persist_content(session, result, source, body.url)
    _persist_content_risk(session, result, source, body.url)
    return result


MAX_CHAT_BYTES = 20 * 1024 * 1024


@router.post("/chat")
def analyze_chat_export(
    file: UploadFile | None = File(None),
    text: str = Form(""),
    demo: str = Form(""),
    principal: Principal = Depends(require_role(Role.ANALYST)),
    session: Session = Depends(get_session),
) -> dict:
    """Analyse a whole group: Telegram export (result.json), WhatsApp export (.txt) or pasted chat."""
    from app.services.safenet.group import analyze_chat, parse_chat

    filename = ""
    if demo:
        from app.services.safenet.demo import demo_chat_bytes
        try:
            raw, filename = demo_chat_bytes(demo)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Нет такого демо-чата") from exc
    elif file is not None:
        raw = file.file.read(MAX_CHAT_BYTES + 1)
        filename = file.filename or "chat"
        if len(raw) > MAX_CHAT_BYTES:
            raise HTTPException(status_code=413, detail="Файл слишком большой (макс. 20 МБ)")
    else:
        raw = text.encode("utf-8")
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Пустой экспорт чата")

    export = parse_chat(raw, filename)
    if not export.messages:
        raise HTTPException(status_code=422, detail="Не удалось распознать сообщения в экспорте")
    record_action(session, principal.subject, "analyze.chat", f"{export.platform}:{len(export.messages)}")

    import hashlib
    cid = hashlib.sha256(raw).hexdigest()
    result = analyze_chat(export, evidence_ids=[cid])
    result["sha256"] = cid
    _persist_group(session, result, raw, cid)
    return result


def _persist_group(session, result: dict, raw: bytes, cid: str) -> None:
    """Group -> Content + ContentRisk (review queue) + graph (members ↔ identifiers)."""
    from app.db.models import Content
    from app.db.risk_repo import upsert_content_risk

    source = {"telegram": "telegram_group", "whatsapp": "whatsapp_group"}.get(result["platform"], "chat")
    group_name = f"group:{result['group']}"[:250]
    try:          # chain of custody for the export itself (best-effort if storage is down)
        from app.core.config import settings
        from app.db.clients import minio_client
        from app.db.evidence_repo import upsert_evidence
        from app.services.evidence import EvidenceStore
        ref = EvidenceStore(minio_client(), settings.minio_raw_bucket, settings.minio_evidence_bucket) \
            .store(raw, source, content_type="text/plain", ext="txt")
    except Exception:  # noqa: BLE001
        ref = None
    row = session.get(Content, cid)
    if row is None:
        row = Content(id=cid, external_id=cid, sha256=cid)
        session.add(row)
    row.source, row.author, row.url = source, group_name, ""
    risk = result["risk"]
    row.lang = risk.get("language") or "ru"
    row.caption = "\n".join(f"{m['author']}: {m['text']}" for m in result["top_messages"])[:20000]
    row.promises_returns = any(s["signal"] in ("pyramid.unrealistic_return", "pyramid.recruitment_income")
                               for s in risk.get("signals", []))
    row.has_referral = any(s["signal"] == "pyramid.referral" for s in risk.get("signals", []))
    row.gambling_content = any(s["signal"] in ("casino.gambling", "casino.brand") for s in risk.get("signals", []))
    session.commit()
    if ref is not None:
        try:
            upsert_evidence(session, cid, ref.sha256, ref.evidence_key, ref.size, "text/plain")
        except Exception:  # noqa: BLE001
            session.rollback()
    crow = upsert_content_risk(
        session, cid, risk["score"], risk["threat_level"], risk["breakdown"], risk["recommendation"],
        author=group_name, source=source, url="", reach={"views": result["messages"]},
        track=risk.get("track", ""), lang=risk.get("language", ""),
    )
    result["content_risk_id"] = crow.id
    try:
        from app.db.clients import neo4j_driver
        from app.services.graph_builder import Edge, GraphBuilder
        gb = GraphBuilder(neo4j_driver())
        ids = result.get("identifiers", {})
        key_people = [result.get("organizer")] + list(result.get("curators", []))
        for person in [p for p in key_people if p]:
            gb.link_identifiers(person, phones=ids.get("phones", []), cards=ids.get("cards", []),
                                telegram=ids.get("telegram", []), domains=ids.get("domains", []),
                                promo_codes=ids.get("promo_codes", []), short_links=ids.get("short_links", []),
                                source="chat")
        prov = {"confidence": 1.0, "source": "chat", "evidence_id": cid, "ts": ""}
        for m in result.get("members", [])[:40]:
            rel = "ORGANIZES" if m["role"].startswith("организатор") else (
                "CURATES" if m["role"].startswith("куратор") else "MEMBER_OF")
            gb.upsert_edge(Edge("Account", m["author"], rel, "Infrastructure", group_name, dict(prov)))
    except Exception:  # noqa: BLE001 — graph is best-effort
        pass
