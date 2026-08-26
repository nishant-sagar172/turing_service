from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    contact_email: str | None = Field(default=None, max_length=256)


class RegisterResponse(BaseModel):
    status: str
    message: str
