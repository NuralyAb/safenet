"""Serializable data passed between the Investigator workflow and its activities.

Plain dataclasses — Temporal's default JSON data converter encodes/decodes them
with type fidelity. Keep these free of I/O and heavy imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InvestigationInput:
    target: str            # "@money_fast"
    requested_by: str      # analyst id — written to the audit log


@dataclass
class ProfileData:
    target: str
    content_ids: list[str] = field(default_factory=list)
    telegram: list[str] = field(default_factory=list)
    wallets: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    has_license: bool = False
    promises_returns: bool = False
    has_referral: bool = False
    gambling_content: bool = False


@dataclass
class SchemeMatch:
    content_id: str
    author: str
    score: float
    shared_identifiers: list[str]


@dataclass
class NetworkSummary:
    related_objects: int = 0
    accounts: int = 0
    telegram_channels: int = 0
    wallets: int = 0
    websites: int = 0
    community_id: int | None = None


@dataclass
class RiskResult:
    score: int
    threat_level: str
    breakdown: list[dict] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class InvestigationReport:
    target: str
    category: str
    risk: RiskResult
    findings: list[str] = field(default_factory=list)
    scheme_matches: int = 0
    network: NetworkSummary = field(default_factory=NetworkSummary)
    narrative: str = ""
