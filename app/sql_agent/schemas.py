"""Request and response schemas for the SQL Builder Agent API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BuildStatus = Literal["built", "clarify_needed", "blocked", "repair_exhausted"]


class BuildQueryRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=4000,
        description="Natural-language question to convert into SQL.",
    )
    workspace: str = Field(
        default="kalaam",
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
        description="Workspace slug. Only 'kalaam' is currently supported.",
    )


class BuildQueryResponse(BaseModel):
    status: BuildStatus = Field(description="Handled build outcome.")
    sql: str | None = Field(default=None, description="Validated SQL when status is built.")
    dialect: str = Field(default="postgresql", description="SQL dialect.")
    validated: bool = Field(default=False, description="True when static and enabled runtime validation passed.")
    explanation: str | None = Field(default=None, description="Model explanation of the built SQL.")
    tables_used: list[str] = Field(default_factory=list, description="Physical tables used by the SQL.")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Model confidence.")
    critic_notes: str | None = Field(default=None, description="Semantic critic notes.")
    clarifying_question: str | None = Field(default=None, description="Question for the caller when ambiguous.")
    reason: str | None = Field(default=None, description="Reason for blocked or failed handled outcomes.")
