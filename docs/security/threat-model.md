# AFM — Threat Model (STRIDE)

**Scope:** on-prem fraud-intelligence platform, law-enforcement deployment. Special-category data: biometric embeddings (face/voice), surveillance targets' PII, evidence. **Assets to protect:** evidence integrity (chain of custody), biometric vault, audit trail, analyst identities, investigation results.

Method: STRIDE per DFD element + DREAD scoring (via `senior-security/threat_modeler.py`). Secret scan: **0 findings**. Legend: ✅ implemented · ⚠️ designed, not enforced · ❌ gap.

---

## Trust boundaries & DFD elements

```
[Hostile sources] ──(untrusted media)──▶ Collectors ──▶ Evidence Store (raw + WORM)
                                              │                  │
                                              ▼                  ▼
                                   GPU Processing ───▶ Fingerprint(Qdrant) / Graph(Neo4j)
                                                                 │
[Analyst] ──(authn)──▶ API ──▶ AI Investigator(Temporal) ──▶ Risk Engine ──▶ Dashboard
                        │                                                        
                        └──▶ Audit Log
```

External entities: **hostile content sources** (fully untrusted), **analysts**. The collector boundary is the primary attack surface — we ingest attacker-controlled bytes.

---

## Prioritized findings

| # | Element | STRIDE | Risk | Status | Mitigation |
|---|---------|--------|------|--------|-----------|
| 1 | API / endpoints | **E / S** | **HIGH** | ❌ | No authn/authz yet. Add OAuth2/OIDC + MFA (FIDO2) for analysts, server-side RBAC on every endpoint, JIT/JEA for the biometric vault. **Block real data until done.** |
| 2 | Audit log | **R** | **HIGH** | ⚠️ | Make append-only + **hash-chained** (each entry hashes the previous). A surveillance tool must prove who-viewed-what; a mutable log is repudiable. |
| 3 | Biometric vault | **I** | **HIGH** | ⚠️ | Encrypt embeddings at rest (AES-256-GCM), separate schema + RBAC + audit, key in KMS/HSM. Currently only designed. |
| 4 | Collectors / processing | **T / D** | **MEDIUM** | ❌ | We decode attacker media (ffmpeg/Whisper/PIL = CVE surface). Sandbox GPU workers: **no outbound network**, resource/time limits, transcode-in-jail, reject malformed input. Rate-limit + bounded queue (DoS). |
| 5 | Evidence WORM | **T** | **MEDIUM** | ✅/⚠️ | Object-lock uses GOVERNANCE (admin can bypass). Use **COMPLIANCE mode + legal hold** for true immutability. SHA-256 at collect ✅. |
| 6 | Chain of custody | **T / R** | **MEDIUM** | ⚠️ | Hash-on-store ✅ but unsigned. Add **Ed25519 signature** over an evidence manifest (sha256 + source + collected_at + collector_id) → verifiable custody, not just a hash. |
| 7 | Temporal workflow | **I** | **MEDIUM** | ❌ | Workflow history holds target PII. Add an **encryption codec** (payload encryption at rest). Replay already aids audit ✅. |
| 8 | AI Investigator (LLM) | **T** | **MEDIUM** | ✅/⚠️ | Collected text is untrusted → prompt-injection risk. Blast radius is bounded because the **LLM never scores or acts — it only narrates established facts** ✅. Still: sanitize, and never let LLM output drive control flow. |
| 9 | Risk decisions | **R / T** | LOW | ✅ | Deterministic, explainable, evidence-linked scoring ✅; human-in-the-loop ER (`AUTO_CONFIRM_FORBIDDEN`) ✅ — both resist "the model decided" repudiation and false-identity tampering. |
| 10 | Dashboard / perimeter | **S / I** | LOW | ⚠️ | TLS 1.3 at perimeter, security headers (CSP `default-src 'self'`, HSTS, X-Frame-Options DENY), short-lived sessions (HttpOnly/Secure/SameSite). |

---

## Defense-in-depth summary (already in the design)

- **Data:** WORM evidence, SHA-256 custody, on-prem only (no external API calls), biometric vault.
- **Application:** deterministic explainable scoring, human-in-the-loop identity, parameterized DB access (SQLAlchemy), content-addressed idempotency.
- **Process integrity:** Temporal replay = auditable investigations.

## Must-fix before handling real data (Phase 0 security)
1. **#1 authn/authz + RBAC** — ✅ implemented (`core/security.py`: argon2 + short-lived JWT + `require_role` + TOTP; endpoints guarded). ⚠️ remaining wiring: Postgres `users` repo, refresh-token flow.
2. **#2 hash-chained audit log** — ✅ DONE: tamper-evident chain persisted to append-only `audit_log` table (DB trigger blocks UPDATE/DELETE) via `db/audit_repo.py`; recorded from investigation/graph/evidence/money-flow endpoints. Also added: rate limiting on login (`ratelimit.py`) and refresh tokens.
3. **#3 biometric encryption-at-rest + vault isolation** — ✅ AES-256-GCM helper implemented + tested (`services/crypto.py`); fail-closed config rejects default secrets in prod. ⚠️ remaining: KMS/HSM key source, separate vault schema + RBAC enforcement.
4. **#4 sandbox media processing** — ✅ SSRF guard implemented + tested (`services/ssrf.py`); `processing-worker` network-isolated (no egress) in compose. ⚠️ remaining: resource/time limits, DNS-rebinding pin at the HTTP-client layer.

Status: code-level controls landed and unit-tested; the ⚠️ items are integration wiring. Re-run this model after the user store, audit persistence, and collectors land (they change the attack surface).
