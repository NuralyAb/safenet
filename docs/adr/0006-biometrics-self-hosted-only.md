# ADR-0006 — Biometric recognition is self-hosted-only

**Status:** Accepted · **Date:** 2026-06-23

## Context
The ТЗ requires face/voice "Same Person Detection". External APIs (OpenAI/Anthropic) **do not offer face/voice recognition** — there is no way to get comparable identity embeddings from them. Biometrics are also special-category data with strict handling rules.

## Decision
Implement the full **entity-resolution machinery** as pure, tested code: cosine similarity signals → a `SAME_PERSON` **candidate** with confidence (`biometrics.py`), human-in-the-loop confirmation (`AUTO_CONFIRM_FORBIDDEN`, `POST /graph/same-person`), and AES-GCM encryption of embeddings at rest (`crypto.py`). The **embedding extraction** is routed to the `local` provider only (InsightFace for face, pyannote/ECAPA for voice) — `get_face_embedder()`/`get_speaker_embedder()` always return `LocalProvider`, which raises a clear error without a GPU.

Conservative scoring: even perfect face+voice gives confidence 0.7 (WEAK) — biometrics alone never reach "strong" without corroboration, and never auto-confirm.

## Consequences
- ✅ The valuable, novel part (ER + human-in-the-loop + encrypted vault) is built and tested now.
- ✅ Honest: no pretense of biometric matching via external APIs.
- ➖ Actual recognition needs `AI_PROVIDER=local` + GPU.

## Alternatives considered
- **Cloud face API (AWS Rekognition / Azure Face)** — another external PII dependency, sends biometrics off-perimeter; rejected for this domain.
