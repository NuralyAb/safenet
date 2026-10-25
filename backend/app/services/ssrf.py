"""SSRF guard for collectors.

Collectors fetch attacker-influenced URLs, so a hostile target could point us at
internal services or the cloud metadata endpoint. Defense:
  1. scheme must be http/https
  2. host must be on the explicit allowlist (primary control)
  3. literal-IP hosts must not be private/loopback/link-local/reserved
     (covers 169.254.169.254 metadata)

Network-level isolation (no outbound egress from processing workers, see
docker-compose `internal` network) is the second layer; this is the first.

NOTE: full DNS-rebinding defense requires resolving + pinning the IP and
re-checking after connect — tracked for the HTTP client layer.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


class UnsafeURLError(ValueError):
    pass


def _is_blocked_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False   # not a literal IP; allowlist is the control
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def check_url(url: str, allowed_hosts: list[str], *, require_allowlist: bool = True) -> str:
    """Return the URL if safe; raise UnsafeURLError otherwise.

    require_allowlist=False (analyst-initiated ad-hoc URL): still block private/
    metadata addresses and non-http schemes, but allow any public host.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not host:
        raise UnsafeURLError("missing host")
    if _is_blocked_ip(host):
        raise UnsafeURLError(f"host resolves to a blocked address: {host}")
    if require_allowlist and host not in allowed_hosts:
        raise UnsafeURLError(f"host not in collector allowlist: {host}")
    return url


def is_safe_url(url: str, allowed_hosts: list[str]) -> bool:
    try:
        check_url(url, allowed_hosts)
        return True
    except UnsafeURLError:
        return False
