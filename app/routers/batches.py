import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext
from app.config import Settings, get_settings
from app.core.voice_engine import VoiceEngineClient, VoiceEngineError
from app.core.csv_utils import CONTACT_COLUMN, recipients_to_csv
from app.db.models import Batch
from app.db.session import get_session
from app.dependencies import get_current_tenant, get_voice_engine
from app.schemas.batches import (
    BatchActionResponse,
    BatchMetricsResponse,
    BatchSummary,
    CreateBatchRequest,
    CreateBatchResponse,
    ScheduleBatchRequest,
    ScheduleBatchResponse,
)
from app.schemas.calls import ExecutionResponse, RetryConfig
from app.services import agent_sync
from app.services.batch_sync import sync_batch_executions
from app.services.store import (
    batch_metrics,
    get_batch_by_voice_id,
    record_batch,
)
from app.services.tenants import get_config
from app.services.variables import check, resolve_variables

router = APIRouter(prefix="/batches", tags=["batches"])


def _default_webhook_url(settings: Settings) -> str | None:
    if settings.turing_public_url:
        return settings.turing_public_url.rstrip("/") + "/webhooks/voice"
    return None


def _encode_retry_config(retry_config: RetryConfig | None) -> str | None:
    if retry_config is None:
        return None
    return json.dumps(retry_config.model_dump(exclude_none=True))


async def _resolve_from_numbers(
    session: AsyncSession, tenant: TenantContext, settings: Settings,
    requested: list[str] | None,
) -> list[str] | None:
    if requested is not None:
        return requested
    config = await get_config(session, tenant.client_id)
    if config and config.default_from_number:
        return [config.default_from_number]
    if settings.voice_default_from_number:
        return [settings.voice_default_from_number]
    return None


async def _get_batch_or_404(
    session: AsyncSession, tenant: TenantContext, batch_id: str
) -> Batch:
    batch = await get_batch_by_voice_id(session, tenant.client_id, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found",
                    "message": f"No batch with id '{batch_id}'."},
        )
    return batch


async def _require_agent_enabled(
    session: AsyncSession, tenant: TenantContext, agent_id: str
) -> None:
    if not await agent_sync.is_agent_enabled(session, tenant.client_id, agent_id):
        raise HTTPException(
            status_code=403,
            detail={"error": "agent_not_enabled",
                    "message": f"Agent '{agent_id}' is not enabled for this client."},
        )


@router.post("", response_model=CreateBatchResponse, status_code=201)
async def create_batch(
    body: CreateBatchRequest,
    validate: bool | None = None,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> CreateBatchResponse:
    await _require_agent_enabled(session, tenant, body.agent_id)

    warnings: list[str] = []
    do_validate = settings.validate_agent_variables if validate is None else validate
    if do_validate:
        contract = await resolve_variables(
            voice_engine, body.agent_id, settings,
            session=session, client_id=tenant.client_id,
        )
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

    from_numbers = await _resolve_from_numbers(
        session, tenant, settings, body.from_phone_numbers
    )
    csv_bytes = recipients_to_csv(body.recipients)
    retry_field = _encode_retry_config(body.retry_config)
    webhook_url = body.webhook_url or _default_webhook_url(settings)

    result = await voice_engine.create_batch(
        agent_id=body.agent_id,
        csv_bytes=csv_bytes,
        from_phone_numbers=from_numbers,
        retry_config=retry_field,
        webhook_url=webhook_url,
    )
    response = CreateBatchResponse.model_validate(result)
    response.warnings = warnings

    await record_batch(
        session,
        client_id=tenant.client_id,
        agent_id=body.agent_id,
        from_number=from_numbers[0] if from_numbers else None,
        retry_config=(
            body.retry_config.model_dump(exclude_none=True)
            if body.retry_config else None
        ),
        recipients=body.recipients,
        total_count=len(body.recipients),
        voice_batch_id=response.batch_id,
        status=response.state,
    )
    return response


@router.post("/upload", response_model=CreateBatchResponse, status_code=201)
async def create_batch_from_csv(
    agent_id: str = Form(...),
    file: UploadFile = File(...),
    from_phone_numbers: str | None = Form(
        default=None, description="JSON array string, e.g. [\"+91...\"].",
    ),
    webhook_url: str | None = Form(default=None),
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> CreateBatchResponse:
    await _require_agent_enabled(session, tenant, agent_id)

    numbers: list[str] | None = None
    if from_phone_numbers is not None:
        try:
            parsed = json.loads(from_phone_numbers)
        except ValueError:
            parsed = None
        numbers = parsed if isinstance(parsed, list) and parsed else None
    if numbers is None:
        numbers = await _resolve_from_numbers(session, tenant, settings, None)

    csv_bytes = await file.read()
    total = max(csv_bytes.count(b"\n") - 1, 0)  # rows minus header (approx.)

    result = await voice_engine.create_batch(
        agent_id=agent_id,
        csv_bytes=csv_bytes,
        file_name=file.filename or "recipients.csv",
        from_phone_numbers=numbers,
        webhook_url=webhook_url or _default_webhook_url(settings),
    )
    response = CreateBatchResponse.model_validate(result)

    await record_batch(
        session,
        client_id=tenant.client_id,
        agent_id=agent_id,
        from_number=numbers[0] if numbers else None,
        retry_config=None,
        recipients=None,  # raw CSV: no structured snapshot
        total_count=total,
        voice_batch_id=response.batch_id,
        status=response.state,
    )
    return response


@router.post("/{batch_id}/schedule", response_model=ScheduleBatchResponse)
async def schedule_batch(
    batch_id: str,
    body: ScheduleBatchRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> ScheduleBatchResponse:
    batch = await _get_batch_or_404(session, tenant, batch_id)

    result = await voice_engine.schedule_batch(batch_id, body.to_voice_engine_payload())
    response = ScheduleBatchResponse.model_validate(result)

    batch.status = response.state or "scheduled"
    batch.scheduled_at = body.scheduled_at
    return response


@router.get("", response_model=list[BatchSummary])
async def list_batches(
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[BatchSummary]:
    """All of this tenant's batches across every agent — unlike ``by-agent``,
    which scopes to a single agent. Reads turing's own records only."""
    filters = [Batch.client_id == tenant.client_id]
    if agent_id:
        filters.append(Batch.agent_id == agent_id)
    if status:
        filters.append(Batch.status == status)
    result = await session.execute(
        select(Batch).where(*filters).order_by(Batch.created_at.desc()).limit(200)
    )
    batches = result.scalars().all()
    return [
        BatchSummary.model_validate({
            "batch_id": batch.voice_batch_id,
            "internal_id": str(batch.id),
            "status": batch.status,
            "agent_id": batch.agent_id,
            "scheduled_at": batch.scheduled_at,
            "from_phone_numbers": [batch.from_number] if batch.from_number else None,
            "valid_contacts": batch.valid_count,
            "total_contacts": batch.total_count,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        })
        for batch in batches
    ]


@router.get("/by-agent/{agent_id}", response_model=list[BatchSummary])
async def list_agent_batches(
    agent_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[BatchSummary]:
    """Reads turing's own records, filtered by tenant — never the live voice
    engine, which has no notion of tenants and would leak other clients'
    batches for the same agent."""
    result = await session.execute(
        select(Batch).where(Batch.client_id == tenant.client_id, Batch.agent_id == agent_id)
        .order_by(Batch.created_at.desc())
    )
    batches = result.scalars().all()
    return [
        BatchSummary.model_validate({
            "batch_id": batch.voice_batch_id,
            "internal_id": str(batch.id),
            "status": batch.status,
            "agent_id": batch.agent_id,
            "scheduled_at": batch.scheduled_at,
            "from_phone_numbers": [batch.from_number] if batch.from_number else None,
            "valid_contacts": batch.valid_count,
            "total_contacts": batch.total_count,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        })
        for batch in batches
    ]


@router.get("/{batch_id}", response_model=BatchSummary)
async def get_batch(
    batch_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> BatchSummary:
    batch = await _get_batch_or_404(session, tenant, batch_id)

    if batch.status not in {"completed", "stopped", "failed", "deleted"}:
        try:
            live = await voice_engine.get_batch(batch_id)
            if isinstance(live, dict):
                if live.get("status"):
                    batch.status = str(live["status"])
                if live.get("valid_contacts") is not None:
                    batch.valid_count = live["valid_contacts"]
                if live.get("scheduled_at"):
                    batch.scheduled_at = str(live["scheduled_at"])
        except VoiceEngineError:
            pass  # serve our record if the engine is unreachable

    return BatchSummary.model_validate(
        {
            "batch_id": batch.voice_batch_id,
            "internal_id": str(batch.id),
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
    background_tasks: BackgroundTasks,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[ExecutionResponse]:
    """Also the reconcile path: every execution the engine returns is
    upserted here, covering any missed webhooks."""
    batch = await _get_batch_or_404(session, tenant, batch_id)
    items = await sync_batch_executions(session, voice_engine, batch, background_tasks, settings)
    return [ExecutionResponse.model_validate(item) for item in items]


@router.get("/{batch_id}/metrics", response_model=BatchMetricsResponse)
async def get_batch_metrics(
    batch_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> BatchMetricsResponse:
    batch = await _get_batch_or_404(session, tenant, batch_id)
    return BatchMetricsResponse(**(await batch_metrics(session, batch)))


@router.post("/{batch_id}/stop", response_model=BatchActionResponse)
async def stop_batch(
    batch_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> BatchActionResponse:
    batch = await _get_batch_or_404(session, tenant, batch_id)

    result = await voice_engine.stop_batch(batch_id)
    response = BatchActionResponse.model_validate(result)
    batch.status = response.state or "stopped"
    return response


@router.delete("/{batch_id}", response_model=BatchActionResponse)
async def delete_batch(
    batch_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> BatchActionResponse:
    batch = await _get_batch_or_404(session, tenant, batch_id)

    result = await voice_engine.delete_batch(batch_id)
    response = BatchActionResponse.model_validate(result)
    batch.status = "deleted"
    return response
