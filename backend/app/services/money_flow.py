"""Money Flow Intelligence — the bridge «соцсеть → кошелёк → биржа».

POSITIONING (deliberate scope): we trace PUBLIC on-chain flow up to the exchange.
We do NOT claim wallet → bank account — that is the agency's data, not ours. The
flow graph carries an explicit BOUNDARY marker: «дальше обогащается вашими данными».
A bridge, not the whole chain — a complement to the agency's systems, not a rival.

Pure (chain detection + exchange tagging + flow assembly) -> unit-tested. The
on-chain query lives behind an OnChainClient (services/chain.py).
"""
from __future__ import annotations

import re

_ETH = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRON = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_BTC = re.compile(r"^(bc1[0-9a-z]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")

BOUNDARY_NOTE = (
    "Дальше — связь «кошелёк → банковский счёт». Она вне публичного on-chain и "
    "обогащается данными профильных ведомств. Мы доводим до кошелька/биржи — это мост, а не вся цепь."
)

# Illustrative exchange tag map (prototype). Production: a maintained address-tag DB.
# Keys MUST be lowercase — tag_exchange lowercases the lookup address.
KNOWN_EXCHANGES: dict[str, str] = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",      # Binance 14 (hot)
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance",      # Binance 8 (cold/hot)
    "0x3cd751e6b0078be393132286c442345e5dc49699": "Coinbase",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",     # Coinbase 1
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",       # Kraken hot
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",          # OKX hot
}


def detect_chain(address: str) -> str | None:
    if _ETH.match(address):
        return "ethereum"
    if _TRON.match(address):
        return "tron"
    if _BTC.match(address):
        return "bitcoin"
    return None


def tag_exchange(address: str, known: dict[str, str] | None = None) -> str | None:
    known = known if known is not None else KNOWN_EXCHANGES
    return known.get(address.lower()) or known.get(address)


def build_flow(account: str, wallets: list[str], onchain_edges: list[dict],
               known_exchanges: dict[str, str] | None = None) -> dict:
    """Assemble account -MENTIONS-> wallet -SENT_TO-> exchange/counterparty, with boundary."""
    nodes: dict[str, str] = {account: "account"}
    edges: list[dict] = []
    for w in wallets:
        nodes[w] = "wallet"
        edges.append({"source": account, "target": w, "label": "MENTIONS",
                      "chain": detect_chain(w)})

    reached = "wallet" if wallets else "account"
    for e in onchain_edges:
        src, dst = e["from"], e["to"]
        exch = tag_exchange(dst, known_exchanges)
        if exch:
            nodes[dst] = "exchange"
            reached = "exchange"
            edges.append({"source": src, "target": dst, "label": "SENT_TO", "exchange": exch})
        else:
            nodes.setdefault(dst, "counterparty")
            edges.append({"source": src, "target": dst, "label": "SENT_TO"})

    return {
        "account": account,
        "nodes": [{"id": k, "type": v} for k, v in nodes.items()],
        "edges": edges,
        "boundary": {"reached": reached, "note": BOUNDARY_NOTE},
    }
