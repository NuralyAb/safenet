"""Domain enrichment via RDAP (the modern, JSON-over-HTTPS successor to WHOIS).

For a domain a scammer advertised we surface registrar, registration/expiry dates,
nameservers and status — extra OSINT for the target portrait. A freshly-registered
domain is itself a fraud signal. RDAP needs no extra dependency (httpx, like the
on-chain client) and no API key. Best-effort: any error yields None, never raises.
"""
from __future__ import annotations

import httpx

_RDAP = "https://rdap.org/domain/{domain}"


def _vcard_field(vcard: list, name: str) -> str | None:
    # vcardArray = ["vcard", [ [name, {}, type, value], ... ]]
    try:
        for entry in vcard[1]:
            if entry[0] == name:
                return entry[3]
    except (IndexError, TypeError):
        pass
    return None


def lookup_domain(domain: str, *, timeout: float = 8.0) -> dict | None:
    """Return {registrar, registered, expires, updated, nameservers, status, age_days}
    for a domain, or None if it can't be resolved (unregistered / RDAP down)."""
    domain = (domain or "").strip().lower().lstrip("@")
    if not domain or "." not in domain:
        return None
    try:
        r = httpx.get(_RDAP.format(domain=domain), timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            return None
        d = r.json()
    except Exception:  # noqa: BLE001 — best-effort enrichment
        return None

    events = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", []) if isinstance(e, dict)}
    registrar = None
    for ent in d.get("entities", []):
        if "registrar" in (ent.get("roles") or []):
            registrar = _vcard_field(ent.get("vcardArray", []), "fn")
            break
    nameservers = [ns.get("ldhName", "").lower() for ns in d.get("nameservers", []) if ns.get("ldhName")]
    registered = events.get("registration")

    age_days = None
    if registered:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(registered.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
        except (ValueError, TypeError):
            pass

    return {
        "domain": domain,
        "registrar": registrar,
        "registered": registered,
        "expires": events.get("expiration"),
        "updated": events.get("last changed") or events.get("last update of RDAP database"),
        "nameservers": nameservers[:4],
        "status": [s for s in (d.get("status") or [])][:4],
        "age_days": age_days,
    }
