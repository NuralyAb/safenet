import json

import httpx
import pytest
import respx

from app.core.config import settings
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.factory import get_embedder, get_llm
from app.services.ai.local_provider import LocalProvider
from app.services.ai.openai_provider import OpenAIProvider

OPENAI = "https://api.openai.com/v1"


# --- factory routing ---------------------------------------------------------
def test_factory_selects_llm_by_provider(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    assert isinstance(get_llm(), OpenAIProvider)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    assert isinstance(get_llm(), AnthropicProvider)
    monkeypatch.setattr(settings, "ai_provider", "local")
    assert isinstance(get_llm(), LocalProvider)


def test_embedder_falls_back_to_openai_for_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    assert isinstance(get_embedder(), OpenAIProvider)   # anthropic has no embeddings


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "bogus")
    with pytest.raises(ValueError):
        get_llm()


# --- OpenAI contract (mocked HTTP, no real calls) ----------------------------
@respx.mock
def test_embed_text_requests_matching_dimensions():
    route = respx.post(f"{OPENAI}/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
    )
    out = OpenAIProvider().embed_text(["scam text"])
    assert out == [[0.1, 0.2, 0.3]]
    # the request asks for the Qdrant collection's dimension
    body = json.loads(route.calls.last.request.read())
    assert body["dimensions"] == settings.dim_text


@respx.mock
def test_chat_completion_returns_content():
    respx.post(f"{OPENAI}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "вывод по фактам"}}]})
    )
    assert OpenAIProvider().complete("sys", "facts") == "вывод по фактам"


@respx.mock
def test_transcribe_returns_text():
    respx.post(f"{OPENAI}/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "вложи 50 тысяч"})
    )
    assert OpenAIProvider().transcribe(b"\x00\x01") == "вложи 50 тысяч"


@respx.mock
def test_vision_tag_parses_comma_list():
    respx.post(f"{OPENAI}/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "casino, slot machine, luxury car"}}]
        })
    )
    tags = OpenAIProvider().tag(b"\xff\xd8\xff")
    assert tags == ["casino", "slot machine", "luxury car"]


@respx.mock
def test_http_error_propagates(monkeypatch):
    monkeypatch.setattr(settings, "ai_max_retries", 0)   # no retry -> fast, still raises
    respx.post(f"{OPENAI}/chat/completions").mock(return_value=httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(httpx.HTTPStatusError):
        OpenAIProvider().complete("s", "u")


@respx.mock
def test_retries_on_429_then_succeeds(monkeypatch):
    # Two 429s then a 200 — the provider should transparently retry and return.
    monkeypatch.setattr(settings, "ai_max_retries", 3)
    monkeypatch.setattr(settings, "ai_retry_base_seconds", 0.0)   # no real sleeping in tests
    responses = [
        httpx.Response(429, json={"error": "rate"}),
        httpx.Response(429, json={"error": "rate"}),
        httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
    ]
    route = respx.post(f"{OPENAI}/chat/completions").mock(side_effect=responses)
    assert OpenAIProvider().complete("s", "u") == "ok"
    assert route.call_count == 3


@pytest.fixture(autouse=True)
def _closed_breaker():
    from app.services.ai import openai_provider
    openai_provider.reset_breaker()
    yield
    openai_provider.reset_breaker()


@respx.mock
def test_insufficient_quota_opens_breaker_and_fails_fast(monkeypatch):
    from app.services.ai.openai_provider import AIUnavailable, breaker_open
    monkeypatch.setattr(settings, "ai_max_retries", 3)
    route = respx.post(f"{OPENAI}/chat/completions").mock(return_value=httpx.Response(
        429, json={"error": {"code": "insufficient_quota", "message": "quota"}}))
    with pytest.raises(httpx.HTTPStatusError):
        OpenAIProvider().complete("s", "u")
    assert route.call_count == 1                  # no pointless retries on an empty balance
    assert breaker_open()
    with pytest.raises(AIUnavailable):            # next call: no network at all
        OpenAIProvider().complete("s", "u")
    assert route.call_count == 1
