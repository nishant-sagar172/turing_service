"""/v1/batches — campaign lifecycle over Bolna's batch APIs, persisted locally.

Create (JSON recipients or raw CSV) -> schedule -> monitor (get/executions/
metrics) -> stop/delete. Every batch is stored in turing's DB; executions are
upserted as they surface (webhooks or the executions listing below).
"""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.bolna_client import BolnaClient, BolnaError
from app.core.csv_utils import CONTACT_COLUMN, recipients_to_csv
from app.db.models import Batch
from app.db.session import get_session
from app.dependencies import get_bolna_client
from app.schemas.batches import (
    BatchActionResponse,
    BatchSummary,
    CreateBatchRequest,
    CreateBatchResponse,
    ScheduleBatchRequest,
    ScheduleBatchResponse,
)
from app.schemas.calls import ExecutionResponse
from app.services.store import (
    batch_metrics,
    get_batch_by_bolna_id,
    record_batch,
    upsert_call_from_execution,
)
from app.services.variables import check, resolve_variables

router = APIRouter(prefix="/batches", tags=["batches"])

_BATCH_TERMINAL = {"completed", "stopped", "failed", "deleted"}


def _default_webhook_url(settings: Settings) -> str | None:
    """Bolna pushes execution updates here (turing's own receiver)."""
    if settings.turing_public_url:
        return settings.turing_public_url.rstrip("/") + "/webhooks/bolna"
    return None


def _encode_optional(from_phone_numbers, retry_config):
    """JSON-encode the optional multipart form fields Bolna expects as strings."""
    from_field = (
        json.dumps(from_phone_numbers) if from_phone_numbers is not None else None
    )
    retry_field = (
        json.dumps(retry_config.model_dump(exclude_none=True))
        if retry_config is not None
        else None
    )
    return from_field, retry_field


async def _get_batch_or_404(session: AsyncSession, batch_id: str) -> Batch:
    batch = await get_batch_by_bolna_id(session, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found",
                    "message": f"No batch with id '{batch_id}'."},
        )
    return batch


@router.post("", response_model=CreateBatchResponse, status_code=201)
async def create_batch(
    request: Request,
    body: CreateBatchRequest,
    validate: bool | None = None,
    client: BolnaClient = Depends(get_bolna_client),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> CreateBatchResponse:
    """Create a batch from a JSON list of recipients (converted to CSV here).

    If ``from_phone_numbers`` is omitted, the configured default
    (``BOLNA_DEFAULT_FROM_NUMBER``) is used when set.

    Unless disabled, each recipient is validated against the agent's required
    variables: any row missing one rejects the whole batch (422); variables no
    row uses are returned as warnings.
    """
    warnings: list[str] = []
    do_validate = settings.validate_agent_variables if validate is None else validate
    if do_validate:
        contract = await resolve_variables(client, body.agent_id, settings)
        row_errors: list[dict[str, object]] = []
        extra_seen: set[str] = set()
        for index, recipient in enumerate(body.recipients):
            provided = {k for k in recipient if k != CONTACT_COLUMN}
            missing, extra = check(provided, contract)
            extra_seen.update(extra)
            if missing:
                row_errors.append({"row": index, "missing": missing})
        if row_errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_required_variables",
                    "agent_id": body.agent_id,
                    "required": contract["required"],
                    "optional": contract["optional"],
                    "rows": row_errors,
                },
            )
        warnings = [
            f"variable '{name}' was sent but the agent's prompt does not use it"
            for name in sorted(extra_seen)
        ]

    from_numbers = body.from_phone_numbers
    if from_numbers is None and settings.bolna_default_from_number:
        from_numbers = [settings.bolna_default_from_number]
    csv_bytes = recipients_to_csv(body.recipients)
    from_field, retry_field = _encode_optional(from_numbers, body.retry_config)
    webhook_url = body.webhook_url or _default_webhook_url(settings)

    result = await client.create_batch(
        agent_id=body.agent_id,
        csv_bytes=csv_bytes,
        from_phone_numbers=from_field,
        retry_config=retry_field,
        webhook_url=webhook_url,
    )
    response = CreateBatchResponse.model_validate(result)
    response.warnings = warnings

    await record_batch(
        session,
        client=getattr(request.state, "api_client", None),
        agent_id=body.agent_id,
        from_number=from_numbers[0] if from_numbers else None,
        retry_config=(
            body.retry_config.model_dump(exclude_none=True)
            if body.retry_config else None
        ),
        recipients=body.recipients,
        total_count=len(body.recipients),
        bolna_batch_id=response.batch_id,
        status=response.state,
    )
    return response


@router.post("/upload", response_model=CreateBatchResponse, status_code=201)
async def create_batch_from_csv(
    request: Request,
    agent_id: str = Form(...),
    file: UploadFile = File(...),
    from_phone_numbers: str | None = Form(
        default=None, description="JSON array string, e.g. [\"+91...\"].",
    ),
    webhook_url: str | None = Form(default=None),
    client: BolnaClient = Depends(get_bolna_client),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> CreateBatchResponse:
    """Create a batch by uploading a raw CSV file (must have a contact_number column)."""
    if from_phone_numbers is None and settings.bolna_default_from_number:
        from_phone_numbers = json.dumps([settings.bolna_default_from_number])
    csv_bytes = await file.read()
    total = max(csv_bytes.count(b"\n") - 1, 0)  # rows minus header (approx.)

    result = await client.create_batch(
        agent_id=agent_id,
        csv_bytes=csv_bytes,
        file_name=file.filename or "recipients.csv",
        from_phone_numbers=from_phone_numbers,
        webhook_url=webhook_url or _default_webhook_url(settings),
    )
    response = CreateBatchResponse.model_validate(result)

    first_from = None
    if from_phone_numbers:
        try:
            parsed = json.loads(from_phone_numbers)
            first_from = parsed[0] if isinstance(parsed, list) and parsed else None
        except ValueError:
            first_from = None
    await record_batch(
        session,
        client=getattr(request.state, "api_client", None),
        agent_id=agent_id,
        from_number=first_from,
        retry_config=None,
        recipients=None,  # raw CSV: no structured snapshot
        total_count=total,
        bolna_batch_id=response.batch_id,
        status=response.state,
    )
    return response


@router.post("/{batch_id}/schedule", response_model=ScheduleBatchResponse)
async def schedule_batch(
    batch_id: str,
    body: ScheduleBatchRequest,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> ScheduleBatchResponse:
    """Schedule a created batch to start (>= 2 min out; rounded to next 10 min)."""
    result = await client.schedule_batch(batch_id, body.to_bolna_payload())
    response = ScheduleBatchResponse.model_validate(result)

    batch = await get_batch_by_bolna_id(session, batch_id)
    if batch is not None:
        batch.status = response.state or "scheduled"
        batch.scheduled_at = body.scheduled_at
    return response


@router.get("/by-agent/{agent_id}", response_model=list[BatchSummary])
async def list_agent_batches(
    agent_id: str,
    client: BolnaClient = Depends(get_bolna_client),
) -> list[BatchSummary]:
    """List all batches created for an agent (live from Bolna)."""
    result = await client.list_agent_batches(agent_id)
    return [BatchSummary.model_validate(item) for item in result]


@router.get("/{batch_id}", response_model=BatchSummary)
async def get_batch(
    batch_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> BatchSummary:
    """Get a batch's status — turing's record, refreshed from Bolna while live."""
    batch = await _get_batch_or_404(session, batch_id)

    if batch.status not in _BATCH_TERMINAL:
        try:
            live = await client.get_batch(batch_id)
            if isinstance(live, dict):
                if live.get("status"):
                    batch.status = str(live["status"])
                if live.get("valid_contacts") is not None:
                    batch.valid_count = live["valid_contacts"]
        except BolnaError:
            pass  # serve our record if Bolna is unreachable

    return BatchSummary.model_validate(
        {
            "batch_id": batch.bolna_batch_id,
            "status": batch.status,
            "agent_id": batch.agent_id,
            "scheduled_at": batch.scheduled_at,
            "from_phone_numbers": [batch.from_number] if batch.from_number else None,
            "valid_contacts": batch.valid_count,
            "total_contacts": batch.total_count,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        }
    )


@router.get("/{batch_id}/executions", response_model=list[ExecutionResponse])
async def get_batch_executions(
    batch_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> list[ExecutionResponse]:
    """List per-call executions in a batch (live from Bolna, persisted here).

    This is also the reconcile path: every execution row Bolna returns is
    upserted into turing's DB, covering any missed webhooks.
    """
    await _get_batch_or_404(session, batch_id)
    result = await client.get_batch_executions(batch_id)

    responses: list[ExecutionResponse] = []
    for item in result if isinstance(result, list) else []:
        if isinstance(item, dict):
            item.setdefault("batch_id", batch_id)
            await upsert_call_from_execution(session, item)
        responses.append(ExecutionResponse.model_validate(item))
    return responses


@router.get("/{batch_id}/metrics")
async def get_batch_metrics(
    batch_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Basic campaign metrics from turing's records: counts, cost, success rate."""
    batch = await _get_batch_or_404(session, batch_id)
    return await batch_metrics(session, batch)


@router.post("/{batch_id}/stop", response_model=BatchActionResponse)
async def stop_batch(
    batch_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> BatchActionResponse:
    """Halt a queued or running batch."""
    result = await client.stop_batch(batch_id)
    response = BatchActionResponse.model_validate(result)
    batch = await get_batch_by_bolna_id(session, batch_id)
    if batch is not None:
        batch.status = response.state or "stopped"
    return response


@router.delete("/{batch_id}", response_model=BatchActionResponse)
async def delete_batch(
    batch_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> BatchActionResponse:
    """Delete a batch on Bolna (turing keeps its historical record)."""
    result = await client.delete_batch(batch_id)
    response = BatchActionResponse.model_validate(result)
    batch = await get_batch_by_bolna_id(session, batch_id)
    if batch is not None:
        batch.status = "deleted"
    return response
