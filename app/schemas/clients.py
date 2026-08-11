from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    contact_email: str | None = None


class RegisterResponse(BaseModel):
    status: str
    message: str
