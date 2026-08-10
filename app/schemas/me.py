from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class MeResponse(BaseModel):
    client_id: uuid.UUID
    name: str
    slug: str
    contact_email: str | None
    status: str
    created_at: datetime
    approved_at: datetime | None
    active_key_count: int
