# ADR-0005 — External AI via a swappable provider abstraction (prototype)

**Status:** Accepted · **Date:** 2026-06-23

## Context
The production target is fully on-prem (no external API calls). But there is no local GPU during prototyping, so self-hosted LLM/embeddings/Whisper/biometrics can't run. We still need the pipeline working end-to-end to demo the killer features.

## Decision
Introduce a **provider abstraction** in `app/services/ai/` — `Embedder/Transcriber/ChatLLM/VisionTagger/FaceEmbedder/SpeakerEmbedder` Protocols. The pipeline depends only on the interfaces. A factory selects the implementation from `AI_PROVIDER` (`openai` | `anthropic` | `local`). Prototype uses OpenAI/Anthropic over raw httpx; production sets `AI_PROVIDER=local` (vLLM/Whisper/InsightFace/pyannote) **without changing call sites**.

**Hard rule:** only **synthetic/demo** data may pass through external APIs (recorded in [CLAUDE.md](../../CLAUDE.md)). Real case/biometric data requires the on-prem `local` provider.

## Consequences
- ✅ Full pipeline runs today; swap to self-hosted is config-only.
- ✅ CI tests mock providers (`respx`) — no network, no cost, deterministic.
- ➖ External APIs are a temporary deviation from the on-prem invariant — mitigated by the synthetic-data rule and the swap path.

## Alternatives considered
- **Wait for GPU / build only on-prem** — blocks the prototype indefinitely.
- **Hard-code OpenAI** — would require a rewrite to go on-prem; rejected.
