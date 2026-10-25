"""On-chain data client — wallet counterparties from public blockchain data.

Behind an interface so the prototype runs without a provider (stub returns no
edges) and a real Etherscan/Tronscan client drops in when a key is configured.
This is the ONLY external reach for money-flow; it stays on the public chain
(wallet → exchange), never touching bank rails.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.core.config import settings


@runtime_checkable
class OnChainClient(Protocol):
    def counterparties(self, address: str, *, limit: int = 50) -> list[dict]: ...


class StubOnChainClient:
    """No provider configured -> no on-chain edges (flow stops at the wallet)."""
    def counterparties(self, address: str, *, limit: int = 50) -> list[dict]:
        return []


class MockOnChainClient:
    """Offline demo client (AI_PROVIDER=mock) — deterministic synthetic flow, no network.

    Each wallet 'sends' to an intermediate wallet + a KNOWN exchange, so Money Flow
    renders account → wallet → counterparty → Binance/Coinbase for the demo accounts
    without an Etherscan key. Deterministic per address (same wallet → same picture).
    """
    _EXCHANGES = (
        "0x28c6c06298d514db089934071355e5743bf21d60",   # Binance (in KNOWN_EXCHANGES)
        "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",   # Coinbase
    )

    def counterparties(self, address: str, *, limit: int = 50) -> list[dict]:
        import hashlib

        h = hashlib.sha256((address or "").encode("utf-8")).hexdigest()
        inter = "0x" + h[:40]                                   # intermediate wallet
        exch = self._EXCHANGES[int(h[:8], 16) % len(self._EXCHANGES)]
        edges = [
            {"to": inter, "value": "1500000000000000000", "hash": "0x" + h[:64]},
            {"to": exch, "value": "920000000000000000", "hash": "0x" + h[8:72]},
        ]
        return edges[: max(1, limit)]


class MockOnChainClient:
    """Offline demo client (AI_PROVIDER=mock) — deterministic synthetic flow, no network.

    Each wallet 'sends' to an intermediate wallet + a KNOWN exchange, so Money Flow
    renders account → wallet → counterparty → Binance/Coinbase for the demo accounts
    without an Etherscan key. Deterministic per address (same wallet → same picture).
    """
    _EXCHANGES = (
        "0x28c6c06298d514db089934071355e5743bf21d60",   # Binance (in KNOWN_EXCHANGES)
        "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",   # Coinbase
    )

    def counterparties(self, address: str, *, limit: int = 50) -> list[dict]:
        import hashlib

        h = hashlib.sha256((address or "").encode("utf-8")).hexdigest()
        inter = "0x" + h[:40]                                   # intermediate wallet
        exch = self._EXCHANGES[int(h[:8], 16) % len(self._EXCHANGES)]
        edges = [
            {"to": inter, "value": "1500000000000000000", "hash": "0x" + h[:64]},
            {"to": exch, "value": "920000000000000000", "hash": "0x" + h[8:72]},
        ]
        return edges[: max(1, limit)]


class EtherscanClient:
    """Public Etherscan txlist -> OUTGOING counterparties (money leaving the wallet).

    Raw httpx (easy to mock with respx, no SDK lock-in — same as the AI providers).
    We surface only outgoing transfers (`from` == wallet): the question Money Flow
    answers is «куда ушли деньги» (wallet → exchange), not who funded the wallet.
    Best-effort: a NOTOK status / empty result / rate-limit yields no edges rather
    than raising, so the flow degrades to «stops at the wallet».
    """
    def __init__(self) -> None:
        self._base = settings.etherscan_base_url
        self._key = settings.etherscan_api_key
        self._chain_id = settings.etherscan_chain_id

    def counterparties(self, address: str, *, limit: int = 50) -> list[dict]:
        with httpx.Client(timeout=30) as c:
            r = c.get(self._base, params={
                "chainid": self._chain_id,   # required by Etherscan API V2
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "page": 1,
                "offset": max(1, limit),
                "apikey": self._key,
            })
            r.raise_for_status()
            data = r.json()

        # status "1" = OK; "0" = "No transactions found" or rate-limited -> empty.
        if str(data.get("status")) != "1" or not isinstance(data.get("result"), list):
            return []

        addr = address.lower()
        out: list[dict] = []
        seen: set[str] = set()
        for tx in data["result"]:
            if str(tx.get("isError", "0")) != "0":          # failed tx -> not a real transfer
                continue
            if (tx.get("from") or "").lower() != addr:      # outgoing only
                continue
            to = (tx.get("to") or "").strip()
            if not to or to.lower() in seen:                # skip contract creation / dedup
                continue
            seen.add(to.lower())
            out.append({"to": to, "value": tx.get("value", "0"), "hash": tx.get("hash", "")})
            if len(out) >= limit:
                break
        return out


def get_onchain_client() -> OnChainClient:
    # Offline demo mode mocks on-chain flow too (no network); otherwise real Etherscan
    # when a key is set, else the empty stub (flow stops at the wallet).
    try:
        from app.services import runtime_config as rc
        if rc.get_value("ai_provider") == "mock" or rc.get_value("mock_money_flow"):
            return MockOnChainClient()
    except Exception:  # noqa: BLE001 — config/DB unavailable -> fall through to real routing
        pass
    return EtherscanClient() if settings.etherscan_api_key else StubOnChainClient()
