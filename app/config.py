"""Application configuration, loaded from environment / .env via pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Values are read from environment variables, falling back to a local .env
    file. Unknown env vars are ignored so the same .env can be shared across
    tools.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "turing_service"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8005

    voice_engine_api_key: str = Field(..., description="Voice engine API key (Bearer token).")
    voice_engine_base_url: str = Field(default="https://api.bolna.ai")
    voice_engine_timeout_seconds: float = Field(default=30.0)
    voice_default_from_number: str | None = Field(
        default=None,
        description="Default caller-ID (E.164) used for calls/batches when the "
        "request does not specify one and the client has no configured "
        "default_from_number. Should be one of the account's owned numbers "
        "(see GET /v1/phone-numbers).",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://turing:turing@localhost:5433/turing_db",
        description="Async SQLAlchemy URL for turing's own Postgres.",
    )

    admin_api_key: str = Field(
        ..., description="Operator credential presented in X-Admin-Key for the "
        "/v1/admin/* surface. Not a tenant identity.",
    )

    turing_public_url: str | None = Field(
        default=None,
        description="Publicly reachable base URL of this service; used as the "
        "webhook_url handed to the voice engine (…/webhooks/voice). If unset, "
        "no webhook is auto-attached (reconcile polling still works).",
    )
    voice_webhook_allowed_ips: str = Field(
        default="",
        description="Comma-separated source IPs allowed to call /webhooks/voice "
        "(Bolna publishes 13.203.39.153). Empty disables the check (dev).",
    )

    agent_variables_file: str = Field(
        default="agent_variables.json",
        description="Path to an optional JSON file marking, per agent_id, which "
        "prompt variables are optional (all others are required). File may be "
        "absent; then every prompt variable is required. Superseded per-client "
        "by client_agent_config.variable_overrides once set.",
    )
    validate_agent_variables: bool = Field(
        default=True,
        description="When true, calls/batches are rejected (422) if a variable "
        "the agent's prompt requires is missing. Can be overridden per request.",
    )

    agent_sync_interval_minutes: float = Field(
        default=15.0,
        description="How often the in-process catalog sync task runs. Set to "
        "<= 0 to disable the periodic task (manual sync via admin endpoint only).",
    )
    api_key_cache_ttl_seconds: float = Field(
        default=60.0,
        description="TTL for the in-memory API-key -> tenant cache. Revocation "
        "/ suspension take effect within this window.",
    )
    register_rate_limit_per_hour: int = Field(
        default=10,
        description="Max POST /v1/register calls accepted per source IP per "
        "hour. Set to <= 0 to disable rate limiting (dev only).",
    )

    redis_url: str | None = Field(
        default=None,
        description="Redis connection URL (redis://:password@host:port/db). "
        "When unset, claim links are disabled and rate limiting falls back to "
        "the in-process rolling-window counter.",
    )
    claim_link_ttl_hours: float = Field(
        default=24.0,
        gt=0,
        description="Lifetime of a one-time claim link in hours. The link is "
        "burned on first POST; TTL is a hard expiry backstop.",
    )
    console_public_url: str | None = Field(
        default=None,
        description="Publicly reachable base URL of the Next.js console "
        "(e.g. http://localhost:3000 in dev). Used to build claim link URLs. "
        "When unset, claim_url is omitted from approve responses.",
    )

    # ── LLM analysis layer ────────────────────────────────────────────────────
    llm_provider: str = Field(
        default="anthropic",
        description="Default LLM provider for call analysis: 'anthropic' or 'openai'. "
        "Overrideable per client via client_config.analysis_llm_provider.",
    )
    llm_model: str | None = Field(
        default=None,
        description="Default model slug. Falls back to claude-haiku-4-5-20251001 "
        "(anthropic) or gpt-4o-mini (openai) when unset.",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key used for call analysis when llm_provider='anthropic'.",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key used for call analysis when llm_provider='openai'.",
    )
    encryption_key: str | None = Field(
        default=None,
        description="Fernet key (base64, 32 bytes) used to encrypt per-client LLM API keys "
        "stored in client_config. Generate with: python -c \"from cryptography.fernet import "
        "Fernet; print(Fernet.generate_key().decode())\"",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def claim_links_enabled(self) -> bool:
        return bool(self.redis_url and self.console_public_url)

    @property
    def voice_webhook_ip_set(self) -> frozenset[str]:
        """Parsed allowlist for /webhooks/voice. Empty = check disabled."""
        return frozenset(
            ip.strip() for ip in self.voice_webhook_allowed_ips.split(",") if ip.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single load per process)."""
    return Settings()  # type: ignore[call-arg]
