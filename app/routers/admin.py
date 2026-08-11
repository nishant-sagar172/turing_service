"""Operator admin surface (/v1/admin/*).

All routes are gated by X-Admin-Key (checked in AuthMiddleware — this router
adds no auth dependency of its own; the middleware denies before the handler
runs).

Key design choices:
- approve uses an explicit commit before minting the claim link so a Redis
  failure never rolls back a successful activation.
- Double-approve is rejected with 409 to prevent duplicate key issuance.
- update_config uses exclude_unset so an omitted field is unchanged; an
  explicit null clears the column.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.core.encryption import EncryptionError, encrypt
from app.core.voice_engine import VoiceEngineClient, VoiceEngineError
from app.db.models import AgentDriftEvent, Batch, Call, CallAnalysis, Client, ClientAgentConfig
from app.db.session import get_session
from app.dependencies import get_redis, get_voice_engine
from app.schemas.admin import (
    AgentConfigUpdate,
    ApproveResponse,
    BatchSummaryAdmin,
    CatalogAgentSummary,
    ClientAgentSummary,
    ClientConfigResponse,
    ClientConfigUpdate,
    ClientPhoneNumberSummary,
    ClientSummary,
    CreateClientRequest,
    IssueKeyRequest,
    IssueKeyResponse,
    KeySummary,
    PhoneNumberCatalogSummary,
    PhoneNumberSyncResponse,
    SetAgentsRequest,
    SetPhoneNumbersRequest,
    SyncResponse,
    UpdateClientRequest,
)
from app.schemas.agents import AgentVariables, DriftEventResponse
from app.schemas.analysis import CallAnalysisResult, CallDetail, CallListItem, CallListResponse
from app.schemas.analytics import AgentStats, AnalyticsOverview, BatchStats, TimeseriesPoint
from app.schemas.common import VoiceEngineStatusResponse
from app.services import agent_sync, analytics as analytics_svc, phone_number_sync, tenants
from app.services import claim_links as cl
from app.services.analysis import analyze_call as _analyze_call
from app.services.store import get_call_by_voice_id
from app.services.variables import resolve_variables

log = logging.getLogger("turing.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_client_or_404(session: AsyncSession, client_id: uuid.UUID) -> Client:
    client = await tenants.get_client(session, client_id)
    if client is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No client with id '{client_id}'."},
        )
    return client


# ── Client lifecycle ──────────────────────────────────────────────────────────

@router.post("/clients", response_model=ClientSummary, status_code=201)
async def create_client(
    body: CreateClientRequest,
    session: AsyncSession = Depends(get_session),
) -> Client:
    try:
        return await tenants.admin_create_client(
            session, name=body.name, contact_email=body.contact_email, status=body.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "conflict", "message": str(exc)})


@router.get("/clients", response_model=list[ClientSummary])
async def list_clients(
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[Client]:
    return await tenants.list_clients(session, status=status)


@router.get("/clients/{client_id}", response_model=ClientSummary)
async def get_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Client:
    return await _get_client_or_404(session, client_id)


@router.patch("/clients/{client_id}", response_model=ClientSummary)
async def update_client(
    client_id: uuid.UUID,
    body: UpdateClientRequest,
    session: AsyncSession = Depends(get_session),
) -> Client:
    client = await _get_client_or_404(session, client_id)
    fields = body.model_dump(exclude_unset=True)
    try:
        return await tenants.update_client(
            session,
            client,
            name=fields.get("name"),
            contact_email=fields.get("contact_email"),
            clear_email="contact_email" in fields and fields["contact_email"] is None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "conflict", "message": str(exc)})


@router.delete("/clients/{client_id}", status_code=204)
async def delete_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    client = await _get_client_or_404(session, client_id)
    await tenants.delete_client(session, client)


@router.post("/clients/{client_id}/approve", response_model=ApproveResponse)
async def approve_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
    settings=Depends(lambda: __import__("app.config", fromlist=["get_settings"]).get_settings()),
) -> ApproveResponse:
    client = await _get_client_or_404(session, client_id)
    if client.status not in {"pending", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_state",
                "message": f"Client is already '{client.status}'. Only pending or rejected clients can be approved.",
            },
        )
    client, raw_key = await tenants.approve_client(session, client, approved_by="admin")
    # Commit before touching Redis so a Redis failure cannot roll back the activation.
    await session.commit()

    claim_url: str | None = None
    if settings.claim_links_enabled:
        try:
            token = await cl.create(
                redis,
                client_id=client.id,
                client_name=client.name,
                raw_key=raw_key,
                ttl_hours=settings.claim_link_ttl_hours,
            )
            if token:
                claim_url = cl.build_claim_url(settings.console_public_url, token)
        except Exception as exc:
            log.warning("claim link creation failed for client %s: %s", client_id, exc)

    return ApproveResponse(
        client_id=client.id,
        status=client.status,
        api_key=raw_key,
        claim_url=claim_url,
    )


@router.post("/clients/{client_id}/reject", response_model=ClientSummary)
async def reject_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Client:
    client = await _get_client_or_404(session, client_id)
    return await tenants.reject_client(client)


@router.post("/clients/{client_id}/suspend", response_model=ClientSummary)
async def suspend_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Client:
    client = await _get_client_or_404(session, client_id)
    return await tenants.suspend_client(client)


@router.post("/clients/{client_id}/reactivate", response_model=ClientSummary)
async def reactivate_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Client:
    client = await _get_client_or_404(session, client_id)
    return await tenants.reactivate_client(client)


# ── API keys ──────────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/keys", response_model=list[KeySummary])
async def list_keys(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list:
    await _get_client_or_404(session, client_id)
    return await tenants.list_keys(session, client_id)


@router.post("/clients/{client_id}/keys", response_model=IssueKeyResponse, status_code=201)
async def issue_key(
    client_id: uuid.UUID,
    body: IssueKeyRequest,
    session: AsyncSession = Depends(get_session),
) -> IssueKeyResponse:
    client = await _get_client_or_404(session, client_id)
    raw_key, key_row = await tenants.issue_key(session, client, label=body.label)
    return IssueKeyResponse(key_id=key_row.id, api_key=raw_key)


@router.delete("/clients/{client_id}/keys/{key_id}", status_code=204)
async def revoke_key(
    client_id: uuid.UUID,
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    key = await tenants.get_key(session, client_id, key_id)
    if key is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No key with id '{key_id}'."},
        )
    tenants.revoke_key(key)


# ── Config ────────────────────────────────────────────────────────────────────

def _config_response(config) -> ClientConfigResponse:
    if config is None:
        return ClientConfigResponse(
            default_from_number=None,
            webhook_url=None,
            webhook_secret_set=False,
            visible_fields=None,
            settings=None,
            analysis_llm_provider=None,
            analysis_llm_model=None,
            analysis_prompt_hint=None,
            analysis_llm_api_key_set=False,
        )
    return ClientConfigResponse(
        default_from_number=config.default_from_number,
        webhook_url=config.webhook_url,
        webhook_secret_set=bool(config.webhook_secret),
        visible_fields=config.visible_fields,
        settings=config.settings,
        analysis_llm_provider=config.analysis_llm_provider,
        analysis_llm_model=config.analysis_llm_model,
        analysis_prompt_hint=config.analysis_prompt_hint,
        analysis_llm_api_key_set=bool(config.analysis_llm_api_key_enc),
    )


@router.get("/clients/{client_id}/config", response_model=ClientConfigResponse)
async def get_config(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ClientConfigResponse:
    await _get_client_or_404(session, client_id)
    config = await tenants.get_config(session, client_id)
    return _config_response(config)


@router.put("/clients/{client_id}/config", response_model=ClientConfigResponse)
async def update_config(
    client_id: uuid.UUID,
    body: ClientConfigUpdate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ClientConfigResponse:
    await _get_client_or_404(session, client_id)

    # Separate the write-only API key from the rest — it needs encryption before storage.
    fields = body.model_dump(exclude_unset=True)
    raw_api_key: str | None = fields.pop("analysis_llm_api_key", None)

    if raw_api_key is not None:
        if not settings.encryption_key:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "encryption_not_configured",
                    "message": "ENCRYPTION_KEY is not set on this server. "
                    "Cannot store per-client API keys.",
                },
            )
        if raw_api_key == "":
            fields["analysis_llm_api_key_enc"] = None  # explicit clear
        else:
            try:
                fields["analysis_llm_api_key_enc"] = encrypt(raw_api_key, settings.encryption_key)
            except EncryptionError as exc:
                raise HTTPException(
                    status_code=500,
                    detail={"error": "encryption_failed", "message": str(exc)},
                ) from exc

    config = await tenants.update_config(session, client_id, **fields)
    return _config_response(config)


# ── Admin batch listing per client ───────────────────────────────────────────

@router.get("/clients/{client_id}/batches", response_model=list[BatchSummaryAdmin])
async def admin_list_client_batches(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[BatchSummaryAdmin]:
    result = await session.execute(
        select(Batch)
        .where(Batch.client_id == client_id)
        .order_by(Batch.created_at.desc())
        .limit(200)
    )
    return [
        BatchSummaryAdmin(
            id=b.id,
            voice_batch_id=b.voice_batch_id,
            agent_id=b.agent_id,
            status=b.status,
            total_count=b.total_count,
            scheduled_at=b.scheduled_at,
            created_at=b.created_at,
        )
        for b in result.scalars().all()
    ]


# ── Admin analytics mirrors ───────────────────────────────────────────────────

@router.get("/clients/{client_id}/analytics/overview", response_model=AnalyticsOverview)
async def admin_analytics_overview(
    client_id: uuid.UUID,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOverview:
    await _get_client_or_404(session, client_id)
    return await analytics_svc.get_overview(
        session, client_id,
        date_from=date_from, date_to=date_to,
        agent_id=agent_id, batch_id=batch_id,
    )


@router.get("/clients/{client_id}/analytics/by-agent", response_model=list[AgentStats])
async def admin_analytics_by_agent(
    client_id: uuid.UUID,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[AgentStats]:
    await _get_client_or_404(session, client_id)
    return await analytics_svc.get_by_agent(
        session, client_id,
        date_from=date_from, date_to=date_to, batch_id=batch_id,
    )


@router.get("/clients/{client_id}/analytics/by-batch", response_model=list[BatchStats])
async def admin_analytics_by_batch(
    client_id: uuid.UUID,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[BatchStats]:
    await _get_client_or_404(session, client_id)
    return await analytics_svc.get_by_batch(
        session, client_id,
        date_from=date_from, date_to=date_to, agent_id=agent_id,
    )


@router.get("/clients/{client_id}/analytics/timeseries", response_model=list[TimeseriesPoint])
async def admin_analytics_timeseries(
    client_id: uuid.UUID,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    granularity: str = Query(default="day", pattern="^(day|week)$"),
    session: AsyncSession = Depends(get_session),
) -> list[TimeseriesPoint]:
    await _get_client_or_404(session, client_id)
    return await analytics_svc.get_timeseries(
        session, client_id,
        date_from=date_from, date_to=date_to,
        agent_id=agent_id, batch_id=batch_id,
        granularity=granularity,
    )


# ── Agents ────────────────────────────────────────────────────────────────────

@router.get("/agents", response_model=list[CatalogAgentSummary])
async def list_catalog_agents(
    session: AsyncSession = Depends(get_session),
) -> list[CatalogAgentSummary]:
    rows = await agent_sync.list_catalog(session)
    return [
        CatalogAgentSummary(
            voice_agent_id=r.voice_agent_id,
            agent_name=r.agent_name,
            agent_status=r.agent_status,
            is_present=r.is_present,
            last_synced_at=r.last_synced_at,
        )
        for r in rows
    ]


@router.get("/agents/{agent_id}/variables", response_model=AgentVariables)
async def get_agent_variables_admin(
    agent_id: str,
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings=Depends(lambda: __import__("app.config", fromlist=["get_settings"]).get_settings()),
    session: AsyncSession = Depends(get_session),
) -> AgentVariables:
    """Admin-scoped variables endpoint — uses X-Admin-Key, not X-API-Key."""
    contract = await resolve_variables(voice_engine, agent_id, settings, session=session)
    return AgentVariables(agent_id=agent_id, **contract)


@router.get("/clients/{client_id}/agents", response_model=list[ClientAgentSummary])
async def get_client_agents(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ClientAgentSummary]:
    await _get_client_or_404(session, client_id)
    rows = await agent_sync.list_client_agent_config(session, client_id)
    return [
        ClientAgentSummary(
            voice_agent_id=cfg.voice_agent_id,
            enabled=cfg.enabled,
            display_name=cfg.display_name,
            variable_overrides=cfg.variable_overrides,
            agent_name=cat.agent_name if cat else None,
            is_present=cat.is_present if cat else None,
        )
        for cfg, cat in rows
    ]


@router.put("/clients/{client_id}/agents", status_code=204)
async def set_client_agents(
    client_id: uuid.UUID,
    body: SetAgentsRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_client_or_404(session, client_id)
    unknown = await agent_sync.unknown_agent_ids(session, body.voice_agent_ids)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_agents",
                "message": "Some agent IDs are not in the catalog.",
                "detail": unknown,
            },
        )
    await agent_sync.set_client_agents(session, client_id, body.voice_agent_ids)


@router.patch("/clients/{client_id}/agents/{voice_agent_id}", status_code=204)
async def patch_client_agent(
    client_id: uuid.UUID,
    voice_agent_id: str,
    body: AgentConfigUpdate,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_client_or_404(session, client_id)
    fields = body.model_dump(exclude_unset=True)
    await agent_sync.update_client_agent_config(
        session, client_id, voice_agent_id, **fields
    )


# ── Drift events ──────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/drift", response_model=list[DriftEventResponse])
async def get_drift(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[DriftEventResponse]:
    await _get_client_or_404(session, client_id)
    events = await agent_sync.list_drift_events(session, client_id)
    return [
        DriftEventResponse(
            id=e.id,
            voice_agent_id=e.voice_agent_id,
            event_type=e.event_type,
            detail=e.detail,
            acknowledged=e.acknowledged,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/clients/{client_id}/drift/{event_id}/acknowledge", status_code=204)
async def acknowledge_drift(
    client_id: uuid.UUID,
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_client_or_404(session, client_id)
    event = await session.get(AgentDriftEvent, event_id)
    if event is None or event.client_id != client_id:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No drift event with id '{event_id}'."},
        )
    event.acknowledged = True


# ── Agent catalog sync ────────────────────────────────────────────────────────

@router.post("/agents/sync", response_model=SyncResponse)
async def sync_agents(
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> SyncResponse:
    result = await agent_sync.sync_catalog(session, voice_engine)
    return SyncResponse(**result)


@router.get("/voice-engine/status", response_model=VoiceEngineStatusResponse)
async def voice_engine_status(
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
) -> VoiceEngineStatusResponse:
    try:
        account = await voice_engine.get_user()
        return VoiceEngineStatusResponse(
            voice_engine="ok",
            base_url=voice_engine.base_url,
            account=account if isinstance(account, dict) else {"data": account},
        )
    except VoiceEngineError as exc:
        return VoiceEngineStatusResponse(
            voice_engine="error",
            base_url=voice_engine.base_url,
            detail=str(exc) + (f" | body={exc.payload}" if exc.payload is not None else ""),
        )


# ── Phone number catalog ──────────────────────────────────────────────────────

@router.get("/phone-numbers", response_model=list[PhoneNumberCatalogSummary])
async def list_phone_number_catalog(
    session: AsyncSession = Depends(get_session),
) -> list[PhoneNumberCatalogSummary]:
    rows = await phone_number_sync.list_catalog(session)
    return [
        PhoneNumberCatalogSummary(
            id=r.id,
            phone_number=r.phone_number,
            telephony_provider=r.telephony_provider,
            rented=r.rented,
            renewal_at=r.renewal_at,
            is_present=r.is_present,
            last_synced_at=r.last_synced_at,
        )
        for r in rows
    ]


@router.post("/phone-numbers/sync", response_model=PhoneNumberSyncResponse)
async def sync_phone_numbers(
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> PhoneNumberSyncResponse:
    result = await phone_number_sync.sync_catalog(session, voice_engine)
    return PhoneNumberSyncResponse(**result)


@router.get(
    "/clients/{client_id}/phone-numbers",
    response_model=list[ClientPhoneNumberSummary],
)
async def get_client_phone_numbers(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ClientPhoneNumberSummary]:
    await _get_client_or_404(session, client_id)
    pairs = await phone_number_sync.list_client_phone_numbers(session, client_id)
    return [
        ClientPhoneNumberSummary(
            id=catalog.id,
            phone_number=catalog.phone_number,
            telephony_provider=catalog.telephony_provider,
            rented=catalog.rented,
            is_present=catalog.is_present,
        )
        for assignment, catalog in pairs
    ]


@router.put("/clients/{client_id}/phone-numbers", status_code=204)
async def set_client_phone_numbers(
    client_id: uuid.UUID,
    body: SetPhoneNumbersRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_client_or_404(session, client_id)
    unknown = await phone_number_sync.unknown_phone_number_ids(
        session, body.phone_number_ids
    )
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_phone_numbers",
                "message": "Some phone number IDs are not in the catalog.",
                "detail": [str(uid) for uid in unknown],
            },
        )
    await phone_number_sync.set_client_phone_numbers(
        session, client_id, body.phone_number_ids
    )


# ── Admin calls ───────────────────────────────────────────────────────────────

def _admin_call_analysis(analysis: CallAnalysis | None) -> CallAnalysisResult | None:
    if analysis is None:
        return None
    return CallAnalysisResult(
        outcome=analysis.outcome,
        summary=analysis.summary,
        reason=analysis.reason,
        requests=analysis.requests or [],
        urgency=analysis.urgency,
        confidence=analysis.confidence,
        symptoms_reported=analysis.symptoms_reported or [],
        model_used=analysis.model_used,
        analyzed_at=analysis.analyzed_at,
    )


async def _admin_from_number(session: AsyncSession, call: Call) -> str | None:
    if call.batch_id is None:
        return None
    batch = await session.get(Batch, call.batch_id)
    return batch.from_number if batch else None


@router.get("/clients/{client_id}/calls", response_model=CallListResponse)
async def admin_list_client_calls(
    client_id: uuid.UUID,
    agent_id: str | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    urgency: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Substring search on contact number."),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> CallListResponse:
    await _get_client_or_404(session, client_id)
    filters = [Call.client_id == client_id]
    if agent_id:
        filters.append(Call.agent_id == agent_id)
    if batch_id:
        filters.append(Call.batch_id == batch_id)
    if status:
        filters.append(Call.status == status)
    if outcome:
        filters.append(CallAnalysis.outcome == outcome)
    if urgency:
        filters.append(CallAnalysis.urgency == urgency)
    if q:
        filters.append(Call.contact_number.ilike(f"%{q}%"))
    if date_from:
        filters.append(Call.created_at >= date_from)
    if date_to:
        filters.append(Call.created_at <= date_to)

    needs_analysis_join = bool(outcome or urgency)

    count_query = select(func.count()).select_from(Call)
    page_query = select(Call).options(selectinload(Call.analysis))
    if needs_analysis_join:
        count_query = count_query.join(CallAnalysis, CallAnalysis.call_id == Call.id)
        page_query = page_query.join(CallAnalysis, CallAnalysis.call_id == Call.id)

    total = (await session.execute(count_query.where(*filters))).scalar_one()

    rows = await session.execute(
        page_query
        .where(*filters)
        .order_by(Call.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    calls = list(rows.scalars().all())

    items: list[CallListItem] = []
    for call in calls:
        items.append(CallListItem(
            call_id=call.voice_call_id,
            agent_id=call.agent_id,
            batch_id=call.batch_id,
            contact_number=call.contact_number,
            from_number=await _admin_from_number(session, call),
            status=call.status,
            duration=call.duration,
            cost=call.cost,
            hangup_reason=call.hangup_reason,
            recording_url=call.recording_url,
            created_at=call.created_at.isoformat() if call.created_at else None,
            analysis=_admin_call_analysis(call.analysis),
        ))

    return CallListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/clients/{client_id}/calls/{call_id}", response_model=CallDetail)
async def admin_get_call(
    client_id: uuid.UUID,
    call_id: str,
    session: AsyncSession = Depends(get_session),
) -> CallDetail:
    await _get_client_or_404(session, client_id)
    call = await get_call_by_voice_id(session, client_id, call_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No call with id '{call_id}'."},
        )
    analysis_row = (await session.execute(
        select(CallAnalysis).where(CallAnalysis.call_id == call.id)
    )).scalar_one_or_none()

    return CallDetail(
        call_id=call.voice_call_id,
        agent_id=call.agent_id,
        batch_id=call.batch_id,
        contact_number=call.contact_number,
        from_number=await _admin_from_number(session, call),
        status=call.status,
        duration=call.duration,
        cost=call.cost,
        hangup_reason=call.hangup_reason,
        recording_url=call.recording_url,
        created_at=call.created_at.isoformat() if call.created_at else None,
        analysis=_admin_call_analysis(analysis_row),
        transcript=call.transcript,
        extracted_data=call.extracted_data,
        patient_ref=call.patient_ref,
        retry_count=call.retry_count,
    )


@router.post("/clients/{client_id}/calls/{call_id}/analyze", response_model=CallAnalysisResult)
async def admin_analyze_call(
    client_id: uuid.UUID,
    call_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CallAnalysisResult:
    await _get_client_or_404(session, client_id)
    call = await get_call_by_voice_id(session, client_id, call_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No call with id '{call_id}'."},
        )
    if not call.transcript:
        raise HTTPException(
            status_code=422,
            detail={"error": "no_transcript", "message": "Call has no transcript — analysis is not possible."},
        )
    client_config = await tenants.get_config(session, client_id)
    analysis = await _analyze_call(session, call, settings, client_config)
    if analysis is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "analysis_failed", "message": "LLM analysis failed. Check API key configuration."},
        )
    return CallAnalysisResult(
        outcome=analysis.outcome,
        summary=analysis.summary,
        reason=analysis.reason,
        requests=analysis.requests or [],
        urgency=analysis.urgency,
        confidence=analysis.confidence,
        symptoms_reported=analysis.symptoms_reported or [],
        model_used=analysis.model_used,
        analyzed_at=analysis.analyzed_at,
    )
