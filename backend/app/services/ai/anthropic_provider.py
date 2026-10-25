"""Anthropic provider — ChatLLM only (no embeddings/STT/vision API).

Used when AI_PROVIDER=anthropic for the Investigator narrative; embeddings and
transcription fall back to OpenAI in the factory.
"""
from __future__ import annotations

import httpx

from app.core.config import settings

_UNSUPPORTED = "Anthropic provider offers chat only; use OpenAI/local for this."


class AnthropicProvider:
    def complete(self, system: str, user: str) -> str:
        with httpx.Client(
            base_url=settings.anthropic_base_url.rstrip("/"),
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=60,
        ) as c:
            r = c.post("/messages", json={
                "model": settings.anthropic_model,
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            })
            r.raise_for_status()
            return r.json()["content"][0]["text"]

    def embed_text(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(_UNSUPPORTED)

    def transcribe(self, audio: bytes, *, filename: str = "audio.mp3") -> str:
        raise NotImplementedError(_UNSUPPORTED)

    def tag(self, image: bytes, *, prompt: str | None = None) -> list[str]:
        raise NotImplementedError(_UNSUPPORTED)
