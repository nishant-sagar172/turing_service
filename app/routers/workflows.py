"""Exposes the calling-workflow registry.

Lets the console build its workflow dropdown from the server rather than
hardcoding the list — registering a new workflow in app/services/workflows.py
makes it selectable with no frontend change.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.workflows import DEFAULT_WORKFLOW_CODE, WORKFLOWS

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowOption(BaseModel):
    workflow_code: str
    label: str
    description: str
    is_default: bool


@router.get("", response_model=list[WorkflowOption])
async def list_workflows() -> list[WorkflowOption]:
    """Selectable calling workflows. Setting one is always optional.

    Codes mirror Kalaam's ``workflows.workflow_code``.
    """
    return [
        WorkflowOption(
            workflow_code=w.code,
            label=w.label,
            description=w.description,
            is_default=w.code == DEFAULT_WORKFLOW_CODE,
        )
        for w in WORKFLOWS.values()
    ]
