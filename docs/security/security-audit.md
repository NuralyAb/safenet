# AFM — SecOps Audit

Gate run via `senior-secops` scanners. Companion to [threat-model.md](threat-model.md).

## Automated scan results

| Scan | Tool | Scope | Result |
|------|------|-------|--------|
| Secrets | `secret_scanner` | backend + frontend/src | ✅ **0** |
| SAST (injection/XSS/cmd/path) | `security_scanner` | backend (32 files) + frontend (10) | ✅ **0** (exit 0) |
| Dependency CVEs | `vulnerability_assessor` | 12 pip + 128 npm packages | ✅ **0** (risk 0/100) |
| Compliance | `compliance_checker --gdpr` | backend | ⚠️ 5 controls flagged — see note |

SAST is clean partly by design: DB access goes through SQLAlchemy (parameterized), the React layer uses `textContent`/JSX (no `innerHTML`), and no `shell=True`/`eval`.

## Compliance — domain interpretation (important)

The scanner assumes consumer SaaS. AFM is a **law-enforcement investigation tool**; in the EU the applicable regime is the **Law Enforcement Directive 2016/680 / national law**, not consumer GDPR. So:

| Flag | Verdict | Action |
|------|---------|--------|
| GDPR-32 Encryption/pseudonymization | **Genuine gap** | Encrypt biometric vault + evidence at rest (AES-256-GCM). Matches threat-model #3. **Fix.** |
| GDPR-25 Data minimization | **Genuine** | Collect/retain only what the mandate requires; purpose-limit; TTL on non-evidence working data. **Fix (policy + retention).** |
| GDPR-33 Incident response (72h) | **Genuine** | Document IR runbook + breach notification path. **Fix (doc).** |
| GDPR-17 Right to erasure | **Context-exempt + by-design conflict** | Largely inapplicable to active LE investigations; **deliberately** in tension with WORM evidence immutability. Document the legal basis; do **not** add blanket erasure. |
| GDPR-20 Data portability | **Context-exempt** | Not applicable to LE processing of suspects. Document and dismiss. |

> Decisions about erasure/portability must be confirmed with legal counsel for the operating jurisdiction — recorded here as an architectural assumption, not legal advice.

## OWASP Top 10 quick-check

| # | Category | Status |
|---|----------|--------|
| A01 Broken Access Control | ❌ API has no authn/authz yet → threat-model #1. **Top priority.** |
| A02 Cryptographic Failures | ⚠️ TLS at perimeter + at-rest encryption pending (#3). No secrets in source ✅. |
| A03 Injection | ✅ Parameterized ORM, no raw SQL, no `eval`. |
| A04 Insecure Design | ✅ Threat model exists; explainable scoring; human-in-the-loop ER. |
| A05 Misconfiguration | ⚠️ `change_me` defaults must be rejected at boot in prod (fail-closed). |
| A06 Vulnerable Components | ✅ 0 CVEs today; add CI gate to keep it that way. |
| A07 Auth Failures | ✅ argon2+TOTP MFA, short-lived JWT + refresh, login rate limiting. |
| A08 Software/Data Integrity | ⚠️ Add artifact signing + SBOM (syft/cosign) in CI; sign evidence manifests (Ed25519). |
| A09 Logging & Monitoring | ✅ Hash-chained audit persisted to append-only table (DB trigger). |
| A10 SSRF | ⚠️ Collectors fetch URLs → block `169.254.169.254` + internal ranges, allowlist hosts. |

## Consolidated must-fix (merged with threat model)

**Before any real data (Phase 0 security):**
1. API **authn/authz + RBAC + MFA** (A01/A07, TM#1).
2. **Hash-chained, append-only audit log** (A09, TM#2).
3. **Encryption at rest** for biometric vault + evidence; fail-closed on default secrets (A02/A05, TM#3, GDPR-32).
4. **Sandbox media processing**: no outbound, resource limits, SSRF host allowlist (A10, TM#4).

**Hardening (next):** Ed25519-signed evidence manifests · Temporal payload encryption codec · WORM COMPLIANCE mode · IR runbook + retention policy · CI security gate (SAST + deps + compliance) · SBOM + signed images.

## Operationalize the gate
A CI workflow at `.github/workflows/security.yml` runs all three scanners on every PR and fails the build on critical findings — so this gate is enforced, not one-off.
