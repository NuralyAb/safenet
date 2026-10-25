"""Live demo: Money Flow on-chain bridge «кошелёк → биржа» (Etherscan API V2).

Proves two things at once, using the REAL code path (no mocks):
  1. The Etherscan API key works on V2 — we pull a wallet's real outgoing transfers.
  2. The Money Flow feature works — those transfers are tagged to a known exchange
     and assembled into account → wallet → exchange, stopping at the boundary.

Run (from backend/):  python3 scripts/demo_money_flow.py [wallet_address]
Reads ETHERSCAN_API_KEY from the environment or the repo-root .env.
"""
from __future__ import annotations

import os
import pathlib
import sys

# Make the `app` package importable when run as a standalone script (backend/ on path).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Load ETHERSCAN_* from the repo-root .env if not already in the environment,
# so the demo runs standalone outside Docker (where env_file injects them).
_root_env = pathlib.Path(__file__).resolve().parents[2] / ".env"
if _root_env.exists():
    for line in _root_env.read_text().splitlines():
        if line.startswith(("ETHERSCAN_API_KEY=", "ETHERSCAN_BASE_URL=")):
            k, _, v = line.partition("=")
            os.environ.setdefault(k, v)

from app.core.config import settings  # noqa: E402
from app.services.chain import get_onchain_client  # noqa: E402
from app.services.money_flow import KNOWN_EXCHANGES, build_flow  # noqa: E402

# A real on-chain wallet that demonstrably deposited ETH to an exchange. In
# production this comes from the Fraud Graph (wallets a scam account advertised);
# here it stands in for «кошелёк, который засветил мошеннический аккаунт».
SUSPECT_ACCOUNT = "@invest_guru_demo"
DEFAULT_WALLET = "0x2b44ebc7d5d308bd7f1cdf44ac892c23a565847a"


def main() -> int:
    wallet = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WALLET

    print("=" * 70)
    print("MONEY FLOW — live on-chain demo (Etherscan V2)")
    print("=" * 70)
    print(f"base_url   : {settings.etherscan_base_url}")
    print(f"chain_id   : {settings.etherscan_chain_id}")
    print(f"api key    : {'set ✓' if settings.etherscan_api_key else 'MISSING ✗ (will use stub)'}")

    client = get_onchain_client()
    print(f"client     : {type(client).__name__}")
    print(f"suspect    : {SUSPECT_ACCOUNT}")
    print(f"wallet     : {wallet}\n")

    print("→ Querying public chain for OUTGOING transfers (куда ушли деньги)...")
    counterparties = client.counterparties(wallet, limit=settings.onchain_counterparty_limit)
    print(f"  got {len(counterparties)} outgoing counterparties from the real chain\n")

    edges = [{"from": wallet, "to": c["to"]} for c in counterparties]
    flow = build_flow(SUSPECT_ACCOUNT, [wallet], edges, KNOWN_EXCHANGES)

    exchanges = [e for e in flow["edges"] if e.get("exchange")]
    print("FLOW GRAPH (account → wallet → counterparty/exchange):")
    for e in flow["edges"]:
        tag = f"  [{e['exchange']}]" if e.get("exchange") else ""
        print(f"  {e['source'][:16]:16} --{e['label']}--> {e['target'][:24]:24}{tag}")

    print(f"\nExchanges identified: {len(exchanges)}")
    for e in exchanges:
        print(f"  • {e['exchange']}  ({e['target']})")

    print(f"\nBoundary reached: {flow['boundary']['reached'].upper()}")
    print(f"  {flow['boundary']['note']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
