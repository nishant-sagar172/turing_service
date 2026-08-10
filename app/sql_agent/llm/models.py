"""Model-agnostic LangChain chat-model factory."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.sql_agent.config import SqlAgentSettings, get_sql_agent_settings

ModelTier = Literal["generate", "select", "prune", "critic", "repair"]


class LLMError(RuntimeError):
    """An LLM provider call or model initialization failed."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


def model_name_for_tier(settings: SqlAgentSettings, tier: ModelTier) -> str:
    if tier == "generate":
        return settings.sql_agent_model_generate
    if tier == "select":
        return settings.sql_agent_model_select
    if tier == "prune":
        return settings.sql_agent_model_prune
    if tier == "critic":
        return settings.sql_agent_model_critic
    return settings.sql_agent_model_repair


def get_chat_model(
    tier: ModelTier,
    settings: SqlAgentSettings | None = None,
) -> BaseChatModel:
    effective_settings = settings or get_sql_agent_settings()
    model_name = model_name_for_tier(effective_settings, tier)
    _seed_provider_environment(effective_settings)
    try:
        return _cached_chat_model(model_name)
    except Exception as exc:
        provider = model_name.split(":", 1)[0] if ":" in model_name else None
        raise LLMError(
            f"Failed to initialize chat model {model_name!r}.",
            provider=provider,
        ) from exc


@lru_cache
def _cached_chat_model(model_name: str) -> BaseChatModel:
    model = init_chat_model(model=model_name)
    if not isinstance(model, BaseChatModel):
        raise LLMError(f"Configured model {model_name!r} is not a chat model.")
    return model


def _seed_provider_environment(settings: SqlAgentSettings) -> None:
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
