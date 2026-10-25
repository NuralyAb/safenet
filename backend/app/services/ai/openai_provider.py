"""OpenAI provider (raw httpx -> easy to mock with respx, no SDK lock-in).

Implements all four interfaces. Embeddings request `dimensions` so the vector
size matches the Qdrant collection (text-embedding-3-large supports truncation).
"""
from __future__ import annotations

import base64
import logging
import random
import time

import httpx

from app.core.config import settings

log = logging.getLogger("afm.ai")

# Statuses worth retrying: 429 (rate limit) + transient 5xx.
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """Parse a Retry-After header (delta-seconds form) if the provider sent one."""
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


class AIUnavailable(RuntimeError):
    """The provider is in cool-down (quota exhausted / sustained 429) — fail fast."""


# Circuit breaker: while open, calls fail immediately instead of waiting out retries,
# so analysis degrades to the deterministic rules in milliseconds, not ~40 s.
_OPEN_UNTIL = 0.0
QUOTA_COOLDOWN_SECONDS = 600.0      # insufficient_quota: billing won't fix itself soon
RATE_COOLDOWN_SECONDS = 60.0        # retries exhausted on 429/5xx


def _open_breaker(seconds: float, why: str) -> None:
    global _OPEN_UNTIL
    _OPEN_UNTIL = time.monotonic() + seconds
    log.warning("AI provider unavailable (%s) — skipping AI calls for %.0fs; rules-only mode", why, seconds)


def breaker_open() -> bool:
    return time.monotonic() < _OPEN_UNTIL


def _quota_exhausted(r: httpx.Response) -> bool:
    if r.status_code != 429:
        return False
    try:
        body = r.json()
    except ValueError:
        return False
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return False
    return err.get("code") == "insufficient_quota" or err.get("type") == "insufficient_quota"


def reset_breaker() -> None:
    global _OPEN_UNTIL
    _OPEN_UNTIL = 0.0


def _send(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    """POST/GET with bounded retry on 429/5xx + exponential backoff (honours Retry-After).

    On the final attempt a still-failing response raises via raise_for_status(), so
    callers see the same httpx.HTTPStatusError as before — just after retries. An
    exhausted quota (or retries exhausted) opens a circuit breaker: later calls raise
    AIUnavailable immediately and every caller falls back to the rules.
    """
    from app.services import runtime_config as rc
    if breaker_open():
        raise AIUnavailable("AI provider in cool-down")
    attempts = max(0, int(rc.get_value("ai_max_retries")))
    base = float(rc.get_value("ai_retry_base_seconds"))
    for i in range(attempts + 1):
        r = client.request(method, url, **kwargs)
        if _quota_exhausted(r):
            _open_breaker(QUOTA_COOLDOWN_SECONDS, "insufficient_quota")
            r.raise_for_status()
        if r.status_code in _RETRY_STATUS and i == attempts and attempts > 0:
            _open_breaker(RATE_COOLDOWN_SECONDS, f"HTTP {r.status_code} after {attempts} retries")
        if r.status_code in _RETRY_STATUS and i < attempts:
            backoff = _retry_after_seconds(r)
            if backoff is None:
                backoff = min(base * (2 ** i), 30.0) + random.uniform(0, base)
            log.warning("AI %s %s -> %s; retry %d/%d in %.1fs",
                        method, url, r.status_code, i + 1, attempts, backoff)
            time.sleep(backoff)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()   # exhausted retries — surface the last error
    return r


class OpenAIProvider:
    def __init__(self) -> None:
        self._base = settings.openai_base_url.rstrip("/")
        self._key = settings.openai_api_key

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base,
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=60,
        )

    def embed_text(self, texts: list[str]) -> list[list[float]]:
        with self._client() as c:
            r = _send(c, "POST", "/embeddings", json={
                "model": settings.openai_embed_model,
                "input": texts,
                "dimensions": settings.dim_text,   # match Qdrant collection
            })
            return [d["embedding"] for d in r.json()["data"]]

    def transcribe(self, audio: bytes, *, filename: str = "audio.mp3") -> str:
        with self._client() as c:
            r = _send(
                c, "POST", "/audio/transcriptions",
                data={"model": settings.openai_stt_model},
                files={"file": (filename, audio)},
            )
            return r.json()["text"]

    def complete(self, system: str, user: str) -> str:
        from app.services import runtime_config as rc
        with self._client() as c:
            r = _send(c, "POST", "/chat/completions", json={
                "model": rc.get_value("ai_chat_model"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            })
            return r.json()["choices"][0]["message"]["content"]

    def ocr(self, image: bytes) -> str:
        b64 = base64.b64encode(image).decode()
        content = [
            {"type": "text", "text": "Извлеки весь текст с изображения. Верни только текст, без пояснений."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        from app.services import runtime_config as rc
        with self._client() as c:
            r = _send(c, "POST", "/chat/completions", json={
                "model": rc.get_value("ai_vision_model"),
                "messages": [{"role": "user", "content": content}],
            })
            return r.json()["choices"][0]["message"]["content"].strip()

    def tag(self, image: bytes, *, prompt: str | None = None) -> list[str]:
        b64 = base64.b64encode(image).decode()
        instruction = prompt or (
            "List fraud-relevant objects you see (casino, slot machine, money, "
            "crypto wallet, luxury car, bank app). Return a comma-separated list."
        )
        content = [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        from app.services import runtime_config as rc
        with self._client() as c:
            r = _send(c, "POST", "/chat/completions", json={
                "model": rc.get_value("ai_vision_model"),
                "messages": [{"role": "user", "content": content}],
            })
            text = r.json()["choices"][0]["message"]["content"]
            return [t.strip() for t in text.split(",") if t.strip()]
