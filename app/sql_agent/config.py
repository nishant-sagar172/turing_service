"""SQL Builder Agent configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SqlAgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    sql_agent_control_db_url: str = Field(
        default="",
        description="Deprecated; not used by the generate-only SQL Builder Agent.",
    )
    kalaam_readonly_database_url: str = Field(
        default="",
        description="Read-only async SQLAlchemy URL for Kalaam EXPLAIN validation.",
    )

    google_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)

    sql_agent_model_generate: str = Field(default="google_genai:gemini-2.5-flash")
    sql_agent_model_select: str = Field(default="google_genai:gemini-2.5-flash")
    sql_agent_model_prune: str = Field(default="google_genai:gemini-2.5-flash")
    sql_agent_model_critic: str = Field(default="google_genai:gemini-2.5-flash")
    sql_agent_model_repair: str = Field(default="google_genai:gemini-2.5-flash")

    sql_agent_embedding_model: str | None = Field(
        default=None,
        description="Deprecated; not used by the generate-only SQL Builder Agent.",
    )
    sql_agent_embedding_dim: int = Field(
        default=1536,
        description="Deprecated; not used by the generate-only SQL Builder Agent.",
    )

    sql_agent_explain_validation: bool = Field(default=True)
    sql_agent_max_repair_attempts: int = Field(default=3, ge=0)
    sql_agent_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    sql_agent_multi_candidate_count: int = Field(default=3, ge=1)
    sql_agent_default_row_limit: int = Field(default=2000, ge=1)
    sql_agent_statement_timeout_ms: int = Field(default=10000, ge=1)


@lru_cache
def get_sql_agent_settings() -> SqlAgentSettings:
    return SqlAgentSettings()
