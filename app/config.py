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

    bolna_api_key: str = Field(..., description="Bolna API key (Bearer token).")
    bolna_base_url: str = Field(default="https://api.bolna.ai")
    bolna_timeout_seconds: float = Field(default=30.0)
    bolna_default_from_number: str | None = Field(
        default=None,
        description="Default caller-ID (E.164) used for calls/batches when the "
        "request does not specify one. Should be one of the account's owned "
        "numbers (see GET /phone-numbers). If unset, Bolna's account default "
        "is used.",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://turing:turing@localhost:5433/turing_db",
        description="Async SQLAlchemy URL for turing's own Postgres.",
    )

    turing_api_keys: str = Field(
        default="dev-turing-key",
        description="Comma-separated API keys accepted in X-API-Key. "
        "CHANGE IN PRODUCTION.",
    )

    turing_public_url: str | None = Field(
        default=None,
        description="Publicly reachable base URL of this service; used as the "
        "webhook_url handed to Bolna (…/webhooks/bolna). If unset, no webhook "
        "is auto-attached (reconcile polling still works).",
    )
    kalaam_webhook_url: str | None = Field(
        default=None,
        description="Kalaam callback endpoint for lean call outcomes "
        "(…/internal/turing/call-completed). If unset, forwarding is disabled.",
    )
    kalaam_webhook_secret: str | None = Field(
        default=None,
        description="HMAC-SHA256 secret used to sign forwarded outcomes "
        "(X-Webhook-Signature).",
    )
    bolna_webhook_allowed_ips: str = Field(
        default="",
        description="Comma-separated source IPs allowed to call /webhooks/bolna "
        "(Bolna publishes 13.203.39.153). Empty disables the check (dev).",
    )

    agent_variables_file: str = Field(
        default="agent_variables.json",
        description="Path to an optional JSON file marking, per agent_id, which "
        "prompt variables are optional (all others are required). File may be "
        "absent; then every prompt variable is required.",
    )
    validate_agent_variables: bool = Field(
        default=True,
        description="When true, calls/batches are rejected (422) if a variable "
        "the agent's prompt requires is missing. Can be overridden per request.",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def api_key_set(self) -> frozenset[str]:
        """Parsed set of accepted X-API-Key values."""
        return frozenset(
            k.strip() for k in self.turing_api_keys.split(",") if k.strip()
        )

    @property
    def bolna_webhook_ip_set(self) -> frozenset[str]:
        """Parsed allowlist for /webhooks/bolna. Empty = check disabled."""
        return frozenset(
            ip.strip() for ip in self.bolna_webhook_allowed_ips.split(",") if ip.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single load per process)."""
    return Settings()
