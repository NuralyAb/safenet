"""License registry check — turns «нелицензионный» from a guess into a verdict.

Before, `has_license` only meant the text *mentioned* a license. Here we verify an
entity (domain / handle / name) against a registry of licensed operators. If a
gambling/investment operator is NOT in the registry, it is treated as unlicensed
(illegal) — which is what the ТЗ word «незаконный» actually requires.

Two backends behind one interface (mirrors services/chain.py):
  - StubRegistryClient — the configured allowlist (prototype default).
  - HttpRegistryClient — a live lookup against the regulator's registry API,
    drop-in when LICENSE_REGISTRY_API_URL is set. Raw httpx (respx-mockable).

The allowlist always short-circuits the live client, so a known-good operator is
recognised even if the API is unreachable (best-effort: API errors degrade to the
allowlist rather than falsely flagging everyone unlicensed).

Pure matching is unit-tested; the live HTTP path is contract-tested on respx.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.core.config import settings


def _norm(s: str) -> str:
    return s.strip().lower().lstrip("@")


def _match_allowlist(identifiers: list[str], registry: list[str]) -> dict:
    """licensed=True iff any identifier is in the allowlist. Returns {licensed, matched, source}."""
    reg = {_norm(r) for r in registry}
    for ident in identifiers:
        if ident and _norm(ident) in reg:
            return {"licensed": True, "matched": ident, "source": "registry"}
    return {"licensed": False, "matched": None, "source": "registry"}


@runtime_checkable
class RegistryClient(Protocol):
    def check(self, identifiers: list[str]) -> dict: ...


class StubRegistryClient:
    """No registry API configured -> match against the configured allowlist."""
    def check(self, identifiers: list[str]) -> dict:
        return _match_allowlist(identifiers, settings.licensed_registry)


class HttpRegistryClient:
    """Live regulator-registry lookup. Allowlist first, then the API per identifier.

    Expected API contract (illustrative — adapt to the regulator): GET with `?q=<id>`
    returning JSON `{"licensed": true|false, ...}`. Any transport/parse error on an
    identifier is skipped (best-effort) so an outage never inflates risk wholesale.
    """
    def __init__(self) -> None:
        self._url = settings.license_registry_api_url
        self._key = settings.license_registry_api_key

    def check(self, identifiers: list[str]) -> dict:
        # Configured allowlist wins — instant, offline, and an explicit override.
        local = _match_allowlist(identifiers, settings.licensed_registry)
        if local["licensed"]:
            return local
        for ident in identifiers:
            if not ident:
                continue
            try:
                with httpx.Client(timeout=15) as c:
                    params = {"q": ident}
                    if self._key:
                        params["apikey"] = self._key
                    r = c.get(self._url, params=params)
                    r.raise_for_status()
                    data = r.json()
            except Exception:  # noqa: BLE001 — best-effort: skip this identifier on any error
                continue
            if isinstance(data, dict) and data.get("licensed"):
                return {"licensed": True, "matched": ident, "source": "regulator-api"}
        return {"licensed": False, "matched": None, "source": "regulator-api"}


def get_registry_client() -> RegistryClient:
    return HttpRegistryClient() if settings.license_registry_api_url else StubRegistryClient()


def check_licensed(identifiers: list[str], registry: list[str] | None = None) -> dict:
    """Verify identifiers against the licensed registry.

    `registry` (explicit allowlist) forces pure offline matching — used by tests and
    callers that supply their own list. Otherwise the configured client decides
    (live API if LICENSE_REGISTRY_API_URL is set, else the configured allowlist).
    """
    if registry is not None:
        return _match_allowlist(identifiers, registry)
    return get_registry_client().check(identifiers)
