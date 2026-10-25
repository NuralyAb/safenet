import httpx
import respx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.license_registry import (
    HttpRegistryClient,
    StubRegistryClient,
    check_licensed,
    get_registry_client,
)

REG = ["profit-x.com", "brokerkz"]
REGISTRY_API = "https://registry.example.gov/check"


def test_licensed_entity_matched_case_insensitive():
    r = check_licensed(["Profit-X.com"], registry=REG)
    assert r["licensed"] is True and r["matched"] == "Profit-X.com"


def test_handle_is_normalized():
    assert check_licensed(["@BrokerKZ"], registry=REG)["licensed"] is True


def test_unlicensed_is_false():
    r = check_licensed(["scam-casino.io"], registry=REG)
    assert r["licensed"] is False and r["matched"] is None


def test_empty_registry_treats_everything_unlicensed():
    # an operator not in the registry -> "нелицензионный", which is the point
    assert check_licensed(["any-casino.com"], registry=[])["licensed"] is False


def test_license_endpoint_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/license/check?q=x").status_code == 401


# --- live regulator-registry client (mocked HTTP, no real calls) -------------
def test_client_routing(monkeypatch):
    monkeypatch.setattr(settings, "license_registry_api_url", "")
    assert isinstance(get_registry_client(), StubRegistryClient)        # no API -> allowlist
    monkeypatch.setattr(settings, "license_registry_api_url", REGISTRY_API)
    assert isinstance(get_registry_client(), HttpRegistryClient)


@respx.mock
def test_http_client_reports_licensed_from_api(monkeypatch):
    monkeypatch.setattr(settings, "license_registry_api_url", REGISTRY_API)
    monkeypatch.setattr(settings, "licensed_registry", [])
    route = respx.get(REGISTRY_API).mock(return_value=httpx.Response(200, json={"licensed": True}))
    r = HttpRegistryClient().check(["legit-broker.kz"])
    assert r["licensed"] is True and r["matched"] == "legit-broker.kz"
    assert r["source"] == "regulator-api" and route.called


@respx.mock
def test_http_client_unlicensed_when_api_says_no(monkeypatch):
    monkeypatch.setattr(settings, "license_registry_api_url", REGISTRY_API)
    monkeypatch.setattr(settings, "licensed_registry", [])
    respx.get(REGISTRY_API).mock(return_value=httpx.Response(200, json={"licensed": False}))
    assert HttpRegistryClient().check(["scam-casino.io"])["licensed"] is False


def test_allowlist_short_circuits_api(monkeypatch):
    # known-good operator is recognised WITHOUT hitting the API (offline override)
    monkeypatch.setattr(settings, "license_registry_api_url", REGISTRY_API)
    monkeypatch.setattr(settings, "licensed_registry", ["profit-x.com"])
    # no respx route registered -> any HTTP call would raise; allowlist must win first
    r = HttpRegistryClient().check(["profit-x.com"])
    assert r["licensed"] is True and r["source"] == "registry"


@respx.mock
def test_http_client_degrades_to_unlicensed_on_api_error(monkeypatch):
    monkeypatch.setattr(settings, "license_registry_api_url", REGISTRY_API)
    monkeypatch.setattr(settings, "licensed_registry", [])
    respx.get(REGISTRY_API).mock(return_value=httpx.Response(500))
    # API down + not in allowlist -> best-effort unlicensed, no exception raised
    assert HttpRegistryClient().check(["anything.io"])["licensed"] is False
