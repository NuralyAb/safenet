"""Pure pipeline helpers (embeddings + fingerprint assembly).

Kept free of Celery / live clients so they unit-test with a fake Embedder.
The Celery tasks (app/workers/tasks.py) build the real embedder/store and call
these.
"""
from __future__ import annotations

from app.services.fingerprint import Fingerprint


# Visual tags that indicate gambling content (drives the risk factor).
_GAMBLING_TAGS = {
    "casino", "slot machine", "slot machines", "slots", "gambling",
    "roulette", "betting", "bookmaker", "poker",
}


def gambling_from_tags(tags) -> bool:
    """Map vision tags -> the gambling_content risk factor."""
    return any(t.strip().lower() in _GAMBLING_TAGS for t in tags)


def facts_from_detection(detection) -> dict:
    """Legacy boolean facts (Content columns, fingerprint, account roll-up) from SafeNet hits."""
    has = detection.has
    return {
        "promises_returns": has("pyramid.unrealistic_return") or has("pyramid.recruitment_income"),
        "has_referral": has("pyramid.referral") or has("pyramid.recruitment_income"),
        "has_license": False,                          # registry-verified below, never from text
        "gambling_content": has("casino.gambling") or has("casino.brand") or has("visual.gambling"),
        "aggressive_investment": has("pyramid.urgency"),
        "hidden_engagement": has("pyramid.closed_chat") or has("casino.proxy_channel"),
    }


def _safe_call(fn, payload):
    """Best-effort optional model call (OCR / biometrics): any failure -> None."""
    try:
        return fn(payload) or None
    except Exception:  # noqa: BLE001
        return None


def extract_features(embedder, collected: dict, *, transcriber=None, vision=None, llm=None,
                     face_embedder=None, speaker_embedder=None, ocr=None,
                     licensed_registry: list[str] | None = None) -> dict:
    """Compute embeddings + carry hard identifiers forward (the 'process' stage).

    - audio + transcriber       -> transcribe (B2) and fold into the text
    - image(s) + ocr            -> on-screen text from every frame -> fold into the text
    - image(s) + vision         -> tag objects (B4) across frames -> gambling_content factor
    - text  + llm               -> NLP content facts (promises/referral/license + intensifiers)
    - image/audio + biometrics  -> face/voice identity embeddings (self-hosted)
    Output satisfies the `_PROCESS_OUT` contract: content_id, sha256, features.

    Multi-frame: when the media enricher provides `images` (a list), OCR and vision
    run over every sampled frame so a marker shown anywhere in the clip is caught,
    not just the one at 1.0s. Single `image` is treated as a one-frame list.
    """
    from app.services.claims import CLAIM_KEYS, SIGNAL_KEYS
    from app.services.safenet import detect

    text = collected.get("text", "")          # caption (+ subtitles from the collector)
    caption = text
    audio = collected.get("audio")
    image = collected.get("image")
    images = collected.get("images") or ([image] if image else [])
    image = image or (images[0] if images else None)   # first frame for single-frame consumers
    transcript = ""                           # speech (Whisper) — retained as evidence text
    ocr_parts: list[str] = []                 # on-screen text per frame — retained as evidence
    if audio and transcriber is not None:
        transcript = _safe_call(transcriber.transcribe, audio) or ""   # best-effort (429/STT down)
        if transcript:
            text = f"{text}\n{transcript}".strip() if text else transcript
    if images and ocr is not None:
        for frame in images:
            on_screen = _safe_call(ocr.ocr, frame)   # «гарантирую 30%» / номер Telegram on the frame
            if on_screen:
                ocr_parts.append(on_screen)
                text = f"{text}\n{on_screen}".strip() if text else on_screen
    ocr_text = "\n".join(ocr_parts)

    tags: list[str] = []
    if images and vision is not None:
        seen: set[str] = set()
        for frame in images:                          # union of tags across frames, order-preserving
            for t in (_safe_call(vision.tag, frame) or []):
                key = t.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    tags.append(t)

    # Biometric identity embeddings (special-category -> encrypt before persistence).
    biometric: dict[str, list[float]] = {}
    if image and face_embedder is not None:
        face = _safe_call(face_embedder.embed_face, image)
        if face:
            biometric["face"] = face
    if audio and speaker_embedder is not None:
        voice = _safe_call(speaker_embedder.embed_voice, audio)
        if voice:
            biometric["voice"] = voice

    # SafeNet KZ detection over the separate evidence segments, so every quote says
    # where it came from (caption / speech / on-screen text / visual tags).
    from app.services import runtime_config as rc
    try:
        use_llm = bool(rc.get_value("safenet_llm_assist"))
    except Exception:  # noqa: BLE001 — settings store unavailable in unit tests
        use_llm = True
    segments = [("caption", caption), ("transcript", transcript), ("ocr", ocr_text)]
    detection = detect([s for s in segments if s[1]], llm=llm if use_llm else None, vision_tags=tags)
    facts = facts_from_detection(detection)
    facts["gambling_content"] = facts["gambling_content"] or gambling_from_tags(tags)
    # registry-verified license overrides the text mention (real «нелицензионный»).
    # Check ALL extracted identifiers (domain / telegram / author handle), not just
    # domains, so a licensed operator is recognised by any of them.
    identifiers = [
        *collected.get("domains", []),
        *collected.get("telegram", []),
        collected.get("author", ""),
    ]
    identifiers = [i for i in identifiers if i]
    if identifiers:
        from app.services.license_registry import check_licensed
        # `licensed_registry` (imported АРРФР data, passed by the DB-aware caller)
        # overrides the env/API path; None falls back to the configured client.
        facts["has_license"] = check_licensed(identifiers, registry=licensed_registry)["licensed"]

    claims = {k: facts[k] for k in CLAIM_KEYS}        # 4-flag contract for downstream/fingerprint
    signals = {k: facts[k] for k in SIGNAL_KEYS}      # intensifiers for graded per-video scoring
    # best-effort: a 429/embeddings outage degrades to "no vector" (no fingerprint
    # match), never a 500 — the deterministic risk is still computed from the facts.
    text_vec = (_safe_call(lambda t: embedder.embed_text([t])[0], text) or []) if text else []
    return {
        "content_id": collected["content_id"],
        "sha256": collected["sha256"],
        "source": collected.get("source", ""),
        "url": collected.get("url", ""),
        "author": collected.get("author", ""),
        "reach": collected.get("reach", {}),   # audience «охват» -> triage priority
        "telegram": collected.get("telegram", []),
        "wallets": collected.get("wallets", []),
        "domains": collected.get("domains", []),
        "text": text,                       # resolved text (caption + transcript + OCR)
        "caption": caption,                 # original post text only
        "safenet": detection.to_dict(),     # SafeNet signals with quotes (scored downstream)
        "phones": detection.identifiers.get("phones", []),
        "cards": detection.identifiers.get("cards", []),
        "promo_codes": detection.identifiers.get("promo_codes", []),
        "short_links": detection.identifiers.get("short_links", []),
        "transcript": transcript,           # speech only (Whisper) — retained as evidence
        "ocr_text": ocr_text,               # on-screen text only — retained as evidence
        "tags": tags,                       # visual object tags (union across frames)
        "claims": claims,                   # NLP claim flags -> risk factors
        "signals": signals,                 # aggressive_investment / hidden_engagement
        "gambling_content": claims["gambling_content"],
        "biometric": biometric,             # face/voice identity embeddings (encrypt at rest)
        "features": {"text": text_vec},
        # Chain-of-custody pass-through (written to the Evidence row at score time).
        "raw_key": collected.get("raw_key", ""),
        "evidence_key": collected.get("evidence_key", collected.get("raw_key", "")),
        "size": collected.get("size", 0),
        "content_type": collected.get("content_type", ""),
    }


def fingerprint_from_processed(processed: dict) -> Fingerprint:
    """Assemble the composite Fingerprint (soft vectors + hard identifiers)."""
    text_vec = processed.get("features", {}).get("text") or []
    return Fingerprint(
        content_id=processed["content_id"],
        author=processed.get("author", ""),
        vectors={"text": text_vec} if text_vec else {},
        telegram=processed.get("telegram", []),
        wallets=processed.get("wallets", []),
        domains=processed.get("domains", []),
    )
