from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that must never reach a production boot (fail-closed). These are the
# .env.example placeholders — if any survive into prod, the process refuses to start.
_FORBIDDEN_SECRETS = {"change_me", "afm", "afm_neo4j", "afm_minio_secret", ""}


class Role(str, Enum):
    """RBAC roles, least-privilege ordered. Biometric vault requires SUPERVISOR+."""
    ANALYST = "analyst"        # run investigations, view non-biometric data
    SUPERVISOR = "supervisor"  # confirm SAME_PERSON links, access biometric vault
    ADMIN = "admin"            # user management, configuration


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Deployment
    app_env: str = "development"   # set APP_ENV=production to enable fail-closed checks

    # Datastores
    database_url: str = "postgresql+psycopg://afm:afm@localhost:5432/afm"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "afm_neo4j"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379/0"

    # Evidence store (chain of custody)
    minio_endpoint: str = "localhost:9000"
    minio_user: str = "afm"
    minio_password: str = "afm_minio_secret"
    minio_raw_bucket: str = "raw"
    minio_evidence_bucket: str = "evidence"

    # Self-hosted LLM (vLLM, OpenAI-compatible) — production target
    llm_base_url: str = "http://localhost:8001/v1"
    llm_model: str = "Qwen2.5-72B-Instruct"

    # AI provider abstraction (prototype: external APIs; production: local).
    # PROTOTYPE RULE: only synthetic/demo data through external providers.
    ai_provider: str = "openai"            # openai | anthropic | local
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embed_model: str = "text-embedding-3-large"
    openai_chat_model: str = "gpt-4o"
    openai_stt_model: str = "whisper-1"
    openai_vision_model: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # AI HTTP resilience — retry transient 429 (rate limit) / 5xx with exponential
    # backoff, honouring the provider's Retry-After header. Tune down in tests.
    ai_max_retries: int = 4
    ai_retry_base_seconds: float = 1.0

    # Embedding dimensions per modality (named vectors in Qdrant).
    # text=bge-m3, visual=SigLIP, audio=CLAP, face=ArcFace.
    dim_text: int = 1024
    dim_visual: int = 1152
    dim_audio: int = 512
    dim_face: int = 512

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "afm-investigations"

    # Auth
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15        # short-lived
    refresh_token_ttl_minutes: int = 60 * 24 * 7   # 7 days
    require_mfa: bool = True              # analysts must present TOTP

    # Data-at-rest encryption (biometric vault). 32-byte key, base64 — from KMS/HSM in prod.
    biometric_encryption_key: str = "change_me"

    # Collector SSRF allowlist — only these hosts may be fetched (the public video
    # webpage URLs; yt-dlp resolves the actual CDN internally). Override via env.
    collector_allowed_hosts: list[str] = [
        "www.youtube.com", "youtube.com", "youtu.be", "m.youtube.com",
        "www.tiktok.com", "tiktok.com", "www.instagram.com", "instagram.com",
        "t.me", "telegram.me",   # public channel web-preview (t.me/s/<channel>)
    ]

    # On-chain (Money Flow) — public blockchain data up to the exchange boundary.
    etherscan_api_key: str = ""
    # Etherscan API V2 (the V1 endpoint api.etherscan.io/api is deprecated/NOTOK).
    # V2 is a single multichain endpoint selected by chainid (1 = Ethereum mainnet).
    etherscan_base_url: str = "https://api.etherscan.io/v2/api"
    etherscan_chain_id: int = 1
    # Max outgoing counterparties pulled per wallet (cost/time control).
    onchain_counterparty_limit: int = 50

    # Continuous monitoring — how often the scheduler sweeps the watchlist.
    watchlist_sweep_seconds: int = 600
    # Max videos to download per account/keyword collection (cost/time control).
    collect_video_limit: int = 10

    # Video analysis — how many frames to sample across each clip for vision/OCR.
    # >1 enables multi-frame analysis (a marker shown anywhere in the clip is caught,
    # not just the frame at 1.0s). 1 keeps the cheap single-frame behaviour.
    video_frames: int = 4

    # Mock Money Flow independently of the AI provider: synthetic wallet→exchange
    # trace even on a live AI run (demo accounts have no real on-chain history).
    mock_money_flow: bool = False

    # Mock the Hunter independently of the AI provider: it synthesizes + scores
    # findings inline (no network / no OpenAI), so the autonomous hunt reliably
    # surfaces accounts on a live AI run (real social search is fragile/ToS-bound).
    mock_hunter: bool = True

    # Mock/offline mode (AI_PROVIDER=mock): artificial delay for the ad-hoc analyze
    # so the demo feels like real processing (download → STT → OCR → vision → NLP)
    # instead of returning instantly. Seconds; 0 = no delay.
    mock_delay_seconds: float = 3.0

    # TikTok ingestion (videos + photo posts). TikTok withholds post data from
    # anonymous datacenter requests, so a logged-in session cookie is required.
    # Paste the raw `Cookie:` header from a logged-in browser. Empty = TikTok links
    # fail with an actionable message. CAVEAT: real-data collection is against ToS
    # and the prototype rule — authorized testing only (see ADR-0005).
    tiktok_cookie: str = ""

    # Instagram ingestion. Instagram blocks anonymous datacenter requests, so
    # yt-dlp needs a logged-in session. Provide EITHER a raw `Cookie:` header from a
    # logged-in browser (INSTAGRAM_COOKIE) — we convert it to a cookie file — OR a
    # path to a Netscape cookies.txt (INSTAGRAM_COOKIES_FILE, takes priority).
    # Empty = Instagram links fail with an actionable message. Authorized use only.
    instagram_cookie: str = ""
    instagram_cookies_file: str = ""

    # License registry — entities verified as licensed (domains/handles/names).
    # Prototype: a configured allowlist; production: a real regulator-registry lookup.
    licensed_registry: list[str] = []
    # Live regulator-registry API. Empty = stub (allowlist only). Set to enable
    # real lookups (GET ?q=<id> -> {"licensed": bool}); allowlist still overrides.
    license_registry_api_url: str = ""
    license_registry_api_key: str = ""

    def assert_production_ready(self) -> None:
        """Fail-closed: refuse to run in production with placeholder secrets."""
        if self.app_env != "production":
            return
        offenders = [
            name for name in ("jwt_secret", "minio_password", "neo4j_password",
                              "biometric_encryption_key")
            if getattr(self, name) in _FORBIDDEN_SECRETS
        ]
        if offenders:
            raise RuntimeError(
                f"Refusing to start: default/placeholder secrets in production: {offenders}"
            )


settings = Settings()
settings.assert_production_ready()
