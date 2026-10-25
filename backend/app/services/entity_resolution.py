"""Entity Resolution — the riskiest module, handled conservatively.

"Same Person Detection" must NEVER auto-assert identity in a law-enforcement
context. Face/voice/handle overlap produces a CANDIDATE link with a confidence
score and the evidence behind it. An analyst confirms it; only then does a
SAME_PERSON edge with confirmed=true enter the Fraud Graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Signal weights for the candidate-link confidence (sum = 1.0)
ER_WEIGHTS = {"face": 0.4, "voice": 0.3, "contact_overlap": 0.2, "behavioral": 0.1}
AUTO_CONFIRM_FORBIDDEN = True   # invariant: identity is never machine-confirmed


@dataclass
class LinkCandidate:
    account_a: str
    account_b: str
    confidence: float
    signals: dict[str, float]            # per-signal similarity in [0,1]
    evidence_ids: list[str] = field(default_factory=list)
    confirmed: bool = False
    confirmed_by: str | None = None

    @property
    def status(self) -> str:
        if self.confirmed:
            return "CONFIRMED"
        return "STRONG_CANDIDATE" if self.confidence >= 0.8 else "WEAK_CANDIDATE"


def score_link(signals: dict[str, float], evidence_ids: list[str],
               account_a: str, account_b: str) -> LinkCandidate:
    confidence = sum(ER_WEIGHTS.get(k, 0) * max(0.0, min(1.0, v))
                     for k, v in signals.items())
    return LinkCandidate(
        account_a=account_a,
        account_b=account_b,
        confidence=round(confidence, 3),
        signals=signals,
        evidence_ids=evidence_ids,
    )


def confirm(candidate: LinkCandidate, analyst_id: str) -> LinkCandidate:
    """Human-in-the-loop confirmation — the ONLY path to a confirmed identity link."""
    candidate.confirmed = True
    candidate.confirmed_by = analyst_id
    return candidate
