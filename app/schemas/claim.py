from __future__ import annotations

from pydantic import BaseModel


class ClaimPeekResponse(BaseModel):
    client_name: str
    expires_in_seconds: int


class ClaimResponse(BaseModel):
    client_name: str
    api_key: str
