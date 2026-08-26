from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
    environment: str


class VoiceEngineStatusResponse(BaseModel):
    voice_engine: str = Field(description="'ok' if the engine responded successfully, else 'error'.")
    base_url: str
    account: dict[str, Any] | None = None
    detail: str | None = None
