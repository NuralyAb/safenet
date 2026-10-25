"""SafeNet KZ — detection of signs of paid lotteries, hidden casino promotion and
financial pyramids in Kazakhstan social media and messengers (RU / KZ / translit).

    analyze_segments([("text", caption), ("ocr", screen_text)]) -> RiskAssessment

Pipeline: normalize (anti-obfuscation views) -> detect (lexicon + numeric + optional
LLM with quote verification) -> score (deterministic per-track formula with gates).
"""
from __future__ import annotations

from app.services import risk_engine
from app.services.safenet.detector import Detection, detect, facts_to_hits
from app.services.safenet.scoring import DISCLAIMER, FLAG_THRESHOLD, assessment_dict, score_detection


def analyze_segments(segments: list[tuple[str, str]], *, llm=None, vision_tags=None,
                     has_license: bool = False, scheme_matches: int = 0, related_objects: int = 0,
                     evidence_ids: list[str] | None = None,
                     use_model: bool = True) -> tuple[risk_engine.RiskAssessment, Detection]:
    detection = detect(segments, llm=llm, vision_tags=vision_tags, use_model=use_model)
    a = score_detection(detection, has_license=has_license, scheme_matches=scheme_matches,
                        related_objects=related_objects, evidence_ids=evidence_ids)
    return a, detection


def analyze_text(text: str, **kw) -> risk_engine.RiskAssessment:
    return analyze_segments([("text", text)], **kw)[0]


__all__ = ["analyze_segments", "analyze_text", "assessment_dict", "detect", "facts_to_hits",
           "score_detection", "DISCLAIMER", "FLAG_THRESHOLD"]
