"""Shared response schemas for the service's own endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness of this service itself (does not touch Bolna)."""

    status: str = "ok"
    service: str
    version: str
    environment: str


class BolnaStatusResponse(BaseModel):
    """Result of probing Bolna connectivity + credential validity."""

    bolna: str = Field(description="'ok' if Bolna responded successfully, else 'error'.")
    base_url: str
    account: dict[str, Any] | None = Field(
        default=None,
        description="Raw account/user payload returned by Bolna when reachable.",
    )
    detail: str | None = Field(
        default=None,
        description="Error detail when the probe fails.",
    )
