"""Biometric entity resolution — "Same Person Detection".

Face/voice identity embeddings -> similarity signals -> a SAME_PERSON *candidate*
with confidence. NEVER auto-confirmed: an analyst must approve before it becomes
a fact in the graph (see entity_resolution.AUTO_CONFIRM_FORBIDDEN).

This module is pure (operates on embeddings) and unit-tested. Producing the
embeddings is self-hosted only (InsightFace/pyannote) — see ai/local_provider.

Embeddings are special-category data: encrypt with crypto.encrypt_embedding
before they touch disk (the biometric vault).
"""
from __future__ import annotations

from app.services.entity_resolution import LinkCandidate, score_link
from app.services.fingerprint import _cosine


def biometric_signals(face_a=None, face_b=None, voice_a=None, voice_b=None) -> dict:
    """Cosine similarity per modality, only where both sides are present."""
    signals: dict[str, float] = {}
    if face_a and face_b:
        signals["face"] = max(0.0, _cosine(face_a, face_b))
    if voice_a and voice_b:
        signals["voice"] = max(0.0, _cosine(voice_a, voice_b))
    return signals


def same_person_candidate(account_a: str, account_b: str, *, face_a=None, face_b=None,
                          voice_a=None, voice_b=None, evidence_ids=None) -> LinkCandidate:
    """Build a SAME_PERSON candidate from biometric similarity. Not a confirmation."""
    signals = biometric_signals(face_a, face_b, voice_a, voice_b)
    return score_link(signals, evidence_ids or [], account_a, account_b)
