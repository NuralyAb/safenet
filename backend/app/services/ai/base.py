"""AI provider interfaces.

The pipeline depends on these Protocols, never on a concrete provider, so the
backend swaps OpenAI/Anthropic (prototype) for self-hosted vLLM/Whisper later by
changing AI_PROVIDER — no call-site changes.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    def embed_text(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio: bytes, *, filename: str = "audio.mp3") -> str: ...


@runtime_checkable
class ChatLLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


@runtime_checkable
class VisionTagger(Protocol):
    def tag(self, image: bytes, *, prompt: str | None = None) -> list[str]: ...


@runtime_checkable
class OCREngine(Protocol):
    def ocr(self, image: bytes) -> str: ...   # on-screen text from a frame


# Biometrics produce IDENTITY embeddings for matching -> self-hosted only
# (no external API offers face/voice recognition). Routed to LocalProvider.
@runtime_checkable
class FaceEmbedder(Protocol):
    def embed_face(self, image: bytes) -> list[float] | None: ...


@runtime_checkable
class SpeakerEmbedder(Protocol):
    def embed_voice(self, audio: bytes) -> list[float] | None: ...
