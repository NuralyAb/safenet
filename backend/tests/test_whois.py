import httpx
import respx

from app.services.whois import lookup_domain

_RDAP = "https://rdap.org/domain/scam-demo.net"
_PAYLOAD = {
    "events": [
        {"eventAction": "registration", "eventDate": "2025-06-22T08:26:08Z"},
        {"eventAction": "expiration", "eventDate": "2026-06-22T08:26:08Z"},
    ],
    "entities": [
        {"roles": ["registrar"],
         "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                  ["fn", {}, "text", "Cloudflare, Inc."]]]},
    ],
    "nameservers": [{"ldhName": "NS1.EXAMPLE.COM"}, {"ldhName": "ns2.example.com"}],
    "status": ["client transfer prohibited"],
}


@respx.mock
def test_parses_rdap_fields():
    respx.get(_RDAP).mock(return_value=httpx.Response(200, json=_PAYLOAD))
    info = lookup_domain("scam-demo.net")
    assert info["registrar"] == "Cloudflare, Inc."
    assert info["registered"].startswith("2025-06-22")
    assert info["expires"].startswith("2026-06-22")
    assert info["nameservers"] == ["ns1.example.com", "ns2.example.com"]
    assert info["age_days"] is not None and info["age_days"] > 0


@respx.mock
def test_unresolved_domain_returns_none():
    respx.get("https://rdap.org/domain/nope.invalid").mock(return_value=httpx.Response(404))
    assert lookup_domain("nope.invalid") is None


def test_blank_or_bad_input_is_none():
    assert lookup_domain("") is None
    assert lookup_domain("not-a-domain") is None
