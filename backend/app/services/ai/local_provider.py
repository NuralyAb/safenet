"""Local (self-hosted) provider — the production target, not wired in the prototype.

Raises a clear error so a misconfigured `AI_PROVIDER=local` fails loudly instead
of silently. Phase: wire vLLM (chat), a local embedding model, and Whisper.
"""
from __future__ import annotations

_MSG = (
    "Local self-hosted AI is not wired yet (no GPU in the prototype). "
    "Set AI_PROVIDER=openai. See docs/PROTOTYPE_ROADMAP.md."
)


class LocalProvider:
    def embed_text(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(_MSG)

    def transcribe(self, audio: bytes, *, filename: str = "audio.mp3") -> str:
        raise NotImplementedError(_MSG)

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError(_MSG)

    def tag(self, image: bytes, *, prompt: str | None = None) -> list[str]:
        raise NotImplementedError(_MSG)

    def ocr(self, image: bytes) -> str:
        # self-hosted PaddleOCR / docTR
        raise NotImplementedError(_MSG)

    def embed_face(self, image: bytes) -> list[float] | None:
        # self-hosted InsightFace/ArcFace
        raise NotImplementedError(_MSG)

    def embed_voice(self, audio: bytes) -> list[float] | None:
        # self-hosted pyannote/ECAPA-TDNN
        raise NotImplementedError(_MSG)
