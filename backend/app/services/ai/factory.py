"""AI provider factory — picks the implementation from settings.ai_provider.

ChatLLM honours the configured provider. Embeddings/STT/vision go through OpenAI
when the provider is `anthropic` (which has no such APIs); `local` routes all to
the self-hosted provider.
"""
from __future__ import annotations

from app.core.config import settings
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import (
    ChatLLM,
    Embedder,
    FaceEmbedder,
    SpeakerEmbedder,
    Transcriber,
    VisionTagger,
)
from app.services.ai.local_provider import LocalProvider
from app.services.ai.mock_provider import MockProvider
from app.services.ai.openai_provider import OpenAIProvider

_VALID = {"openai", "anthropic", "local", "mock"}


def _check(provider: str) -> None:
    if provider not in _VALID:
        raise ValueError(f"Unknown AI_PROVIDER={provider!r}; expected one of {sorted(_VALID)}")


def _provider() -> str:
    """Effective provider — runtime-configurable (UI), falls back to env default."""
    from app.services import runtime_config as rc
    return rc.get_value("ai_provider")


def get_llm() -> ChatLLM:
    provider = _provider()
    _check(provider)
    return {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "local": LocalProvider,
        "mock": MockProvider,
    }[provider]()


def _non_chat():
    provider = _provider()
    _check(provider)
    if provider == "mock":
        return MockProvider()        # fully offline — no external API
    # Anthropic lacks embeddings/STT/vision -> use OpenAI for those.
    return LocalProvider() if provider == "local" else OpenAIProvider()


def get_embedder() -> Embedder:
    return _non_chat()


def get_transcriber() -> Transcriber:
    return _non_chat()


def get_vision_tagger() -> VisionTagger:
    return _non_chat()


def get_ocr():
    """OCR chain: cloud/vision provider first, on-prem Tesseract as fallback.

    In mock/local mode Tesseract goes first so screenshots get their REAL text (the
    mock's canned OCR is only a last resort when Tesseract isn't installed).
    """
    from app.services.ai.ocr_local import ChainOCR, TesseractOCR, tesseract_available

    local = TesseractOCR() if tesseract_available() else None
    provider = _provider()
    if provider in ("mock", "local"):
        return ChainOCR([local, MockProvider() if provider == "mock" else None])
    return ChainOCR([_non_chat(), local])


# Biometrics are self-hosted only — no external API does face/voice recognition.
def get_face_embedder() -> FaceEmbedder:
    return LocalProvider()


def get_speaker_embedder() -> SpeakerEmbedder:
    return LocalProvider()
