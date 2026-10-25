"""Deterministic, explainable risk scoring.

Design principle (law-enforcement grade): the LLM/AI extracts FACTS and evidence;
this engine computes the score deterministically. Every point traces to an
`evidence_id` so the assessment is defensible in a manual/legal review.

Weights come straight from the ТЗ (sum = 100):
    financial_promises      25
    referral_structure      20
    known_scheme_repetition 20
    suspicious_links        15
    gambling_content        10
    infra_anonymity         10
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

FACTOR_WEIGHTS: dict[str, int] = {
    "financial_promises": 25,
    "referral_structure": 20,
    "known_scheme_repetition": 20,
    "suspicious_links": 15,
    "gambling_content": 10,
    "infra_anonymity": 10,
}


class ThreatLevel(str, Enum):
    """SafeNet KZ requires three levels: низкий / средний / высокий."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class FactorSignal:
    """One factor's normalized strength in [0,1] with the evidence backing it."""
    factor: str
    strength: float                       # 0..1, produced by AI extractors
    evidence_ids: list[str] = field(default_factory=list)
    note: str = ""

    def contribution(self) -> float:
        weight = FACTOR_WEIGHTS.get(self.factor, 0)
        return round(weight * max(0.0, min(1.0, self.strength)), 2)


@dataclass
class RiskAssessment:
    score: int
    threat_level: ThreatLevel
    breakdown: list[dict]                  # per-factor: weight, strength, contribution, evidence
    recommendation: str
    # SafeNet KZ per-track details (filled by safenet.scoring; empty for the legacy roll-up)
    track: str = ""                        # lottery | casino | pyramid | ""
    tracks: dict = field(default_factory=dict)
    signals: list[dict] = field(default_factory=list)
    multi_track: list[str] = field(default_factory=list)
    language: str = ""
    disclaimer: str = ""


def _threat_level(score: int) -> ThreatLevel:
    if score >= 65:
        return ThreatLevel.HIGH
    if score >= 40:
        return ThreatLevel.MEDIUM
    return ThreatLevel.LOW


def assess(signals: list[FactorSignal]) -> RiskAssessment:
    """Combine factor signals into a 0-100 score. Unknown factors contribute 0."""
    total = 0.0
    breakdown: list[dict] = []
    for s in signals:
        contribution = s.contribution()
        total += contribution
        breakdown.append(
            {
                "factor": s.factor,
                "weight": FACTOR_WEIGHTS.get(s.factor, 0),
                "strength": round(s.strength, 3),
                "contribution": contribution,
                "evidence_ids": s.evidence_ids,
                "note": s.note,
            }
        )

    score = int(round(min(100.0, total)))
    level = _threat_level(score)
    recommendation = (
        "Признаки возможного нарушения — передать на ручную проверку"
        if level == ThreatLevel.HIGH
        else "Наблюдение, повторная оценка при новых данных"
    )
    return RiskAssessment(
        score=score,
        threat_level=level,
        breakdown=sorted(breakdown, key=lambda b: b["contribution"], reverse=True),
        recommendation=recommendation,
    )
