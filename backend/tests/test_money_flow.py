import httpx
import respx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.chain import (
    EtherscanClient,
    MockOnChainClient,
    StubOnChainClient,
    get_onchain_client,
)
from app.services.money_flow import build_flow, detect_chain, tag_exchange

BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
WALLET = "0x" + "ab" * 20
ETHERSCAN = settings.etherscan_base_url


def test_detect_chain_by_address_format():
    assert detect_chain(BINANCE) == "ethereum"
    assert detect_chain("TJRabPrwbZy45sbavfcjinPJC18kjpRTv8") == "tron"
    assert detect_chain("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4") == "bitcoin"
    assert detect_chain("not-an-address") is None


def test_tag_known_exchange():
    assert tag_exchange(BINANCE) == "Binance"
    assert tag_exchange("0x" + "0" * 40) is None


def test_flow_traces_account_to_wallet_to_exchange_with_boundary():
    flow = build_flow(
        "@scam", wallets=[BINANCE.replace("28c6", "dead")],   # a wallet address
        onchain_edges=[{"from": BINANCE.replace("28c6", "dead"), "to": BINANCE}],
    )
    types = {n["id"]: n["type"] for n in flow["nodes"]}
    assert types["@scam"] == "account"
    assert types[BINANCE] == "exchange"                      # reached the exchange
    assert flow["boundary"]["reached"] == "exchange"
    # the deliberate scope marker — bridge, not the whole chain
    assert "обогащается данными" in flow["boundary"]["note"]
    assert "банковский счёт" in flow["boundary"]["note"]


def test_flow_stops_at_wallet_without_onchain_data():
    flow = build_flow("@scam", wallets=["0x" + "a" * 40], onchain_edges=[])
    assert flow["boundary"]["reached"] == "wallet"
    assert all(e["label"] == "MENTIONS" for e in flow["edges"])


def test_money_flow_endpoint_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/graph/money-flow/@scam").status_code == 401


# --- Etherscan on-chain client (mocked HTTP, no real calls) ------------------
@respx.mock
def test_etherscan_returns_only_outgoing_deduped_counterparties():
    respx.get(ETHERSCAN).mock(return_value=httpx.Response(200, json={
        "status": "1", "message": "OK", "result": [
            {"from": WALLET, "to": BINANCE, "isError": "0", "value": "10", "hash": "0xa"},
            {"from": "0x" + "11" * 20, "to": WALLET, "isError": "0", "value": "5", "hash": "0xb"},   # incoming -> skip
            {"from": WALLET, "to": BINANCE, "isError": "0", "value": "7", "hash": "0xc"},            # dup -> dedup
            {"from": WALLET, "to": "0x" + "22" * 20, "isError": "1", "value": "0", "hash": "0xd"},   # failed -> skip
        ],
    }))
    out = EtherscanClient().counterparties(WALLET)
    assert [c["to"] for c in out] == [BINANCE]      # outgoing-only, success-only, deduped


@respx.mock
def test_etherscan_empty_when_no_transactions():
    respx.get(ETHERSCAN).mock(return_value=httpx.Response(200, json={
        "status": "0", "message": "No transactions found", "result": [],
    }))
    assert EtherscanClient().counterparties(WALLET) == []


@respx.mock
def test_etherscan_respects_limit():
    tos = ["0x" + f"{i:02x}" * 20 for i in range(5)]
    respx.get(ETHERSCAN).mock(return_value=httpx.Response(200, json={
        "status": "1", "result": [
            {"from": WALLET, "to": t, "isError": "0", "value": "1", "hash": "0x"} for t in tos
        ],
    }))
    assert len(EtherscanClient().counterparties(WALLET, limit=3)) == 3


def test_onchain_client_routing(monkeypatch):
    import app.services.runtime_config as rc
    # not mock, money-flow mock OFF (DB-independent)
    monkeypatch.setattr(rc, "get_value", lambda k: "openai" if k == "ai_provider" else False)
    monkeypatch.setattr(settings, "etherscan_api_key", "")
    assert isinstance(get_onchain_client(), StubOnChainClient)   # no key -> flow stops at wallet
    monkeypatch.setattr(settings, "etherscan_api_key", "demo-key")
    assert isinstance(get_onchain_client(), EtherscanClient)


def test_mock_onchain_client_in_mock_mode(monkeypatch):
    import app.services.runtime_config as rc
    monkeypatch.setattr(rc, "get_value", lambda k: "mock" if k == "ai_provider" else None)
    assert isinstance(get_onchain_client(), MockOnChainClient)   # mock mode -> synthetic flow


def test_mock_money_flow_toggle_independent_of_provider(monkeypatch):
    import app.services.runtime_config as rc
    # live AI provider, but the dedicated Money-Flow mock toggle is ON
    monkeypatch.setattr(rc, "get_value",
                        lambda k: True if k == "mock_money_flow" else "openai")
    assert isinstance(get_onchain_client(), MockOnChainClient)


def test_mock_onchain_traces_to_known_exchange():
    out = MockOnChainClient().counterparties("0x" + "ab" * 20)
    assert len(out) == 2                                          # intermediate + exchange
    assert any(tag_exchange(c["to"]) for c in out)               # one hop lands on a known exchange
