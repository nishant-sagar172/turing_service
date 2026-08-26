from __future__ import annotations

import math
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import TenantContext
from app.config import Settings, get_settings
from app.core.voice_engine import VoiceEngineClient, VoiceEngineError
from app.db.models import Call, CallAnalysis
from app.db.session import get_session
from app.dependencies import get_current_tenant, get_voice_engine
from app.schemas.analysis import CallAnalysisResult, CallDetail, CallListItem, CallListResponse
from app.schemas.calls import MakeCallRequest, MakeCallResponse, StopCallResponse
from app.services import agent_sync
from app.services.analysis import analyze_call
from app.services.store import TERMINAL_STATUSES, get_call_by_voice_id, record_call, upsert_call_from_execution
from app.services.tenants import get_config
from app.services.variables import check, resolve_variables

router = APIRouter(prefix="/calls", tags=["calls"])


async def _require_agent_enabled(
    session: AsyncSession, tenant: TenantContext, agent_id: str
) -> None:
    if not await agent_sync.is_agent_enabled(session, tenant.client_id, agent_id):
        raise HTTPException(
            status_code=403,
            detail={"error": "agent_not_enabled",
                    "message": f"Agent '{agent_id}' is not enabled for this client."},
        )


def _analysis_result(analysis: CallAnalysis | None) -> CallAnalysisResult | None:
    return CallAnalysisResult.from_model(analysis)


def _call_list_item(call: Call) -> CallListItem:
    return CallListItem(
        call_id=call.voice_call_id,
        agent_id=call.agent_id,
        batch_id=call.batch_id,
        contact_number=call.contact_number,
        from_number=call.batch.from_number if call.batch else None,
        status=call.status,
        duration=call.duration,
        cost=call.cost,
        hangup_reason=call.hangup_reason,
        recording_url=call.recording_url,
        created_at=call.created_at.isoformat() if call.created_at else None,
        analysis=_analysis_result(call.analysis),
    )


@router.post("", response_model=MakeCallResponse, status_code=201)
async def make_call(
    body: MakeCallRequest,
    validate: bool | None = None,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> MakeCallResponse:
    await _require_agent_enabled(session, tenant, body.agent_id)

    warnings: list[str] = []
    do_validate = settings.validate_agent_variables if validate is None else validate
    if do_validate and body.user_data:
        contract = await resolve_variables(
            voice_engine, body.agent_id, settings,
            session=session, client_id=tenant.client_id,
        )
        provided = set(body.user_data.keys())
        missing, extra = check(provided, contract)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_required_variables",
                    "agent_id": body.agent_id,
                    "required": contract["required"],
                    "optional": contract["optional"],
                    "missing": missing,
                },
            )
        warnings = [
            f"variable '{name}' was sent but the agent's prompt does not use it"
            for name in sorted(extra)
        ]

    # body → tenant config → global settings
    from_phone_number = body.from_phone_number
    if from_phone_number is None:
        config = await get_config(session, tenant.client_id)
        if config and config.default_from_number:
            from_phone_number = config.default_from_number
        elif settings.voice_default_from_number:
            from_phone_number = settings.voice_default_from_number

    payload = body.to_voice_engine_payload()
    if from_phone_number and "from_phone_number" not in payload:
        payload["from_phone_number"] = from_phone_number

    result = await voice_engine.make_call(payload)
    response = MakeCallResponse.model_validate(result)
    response.warnings = warnings

    if response.execution_id:
        await record_call(
            session,
            client_id=tenant.client_id,
            agent_id=body.agent_id,
            voice_call_id=response.execution_id,
            contact_number=body.recipient_phone_number,
            status=response.status or "queued",
        )

    return response


@router.get("", response_model=CallListResponse)
async def list_calls(
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
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> CallListResponse:
    filters = [Call.client_id == tenant.client_id]
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
    page_query = select(Call).options(
        selectinload(Call.analysis), selectinload(Call.batch)
    )
    if needs_analysis_join:
        count_query = count_query.join(CallAnalysis, CallAnalysis.call_id == Call.id)
        page_query = page_query.join(CallAnalysis, CallAnalysis.call_id == Call.id)

    total_row = await session.execute(count_query.where(*filters))
    total = total_row.scalar_one()

    rows = await session.execute(
        page_query
        .where(*filters)
        .order_by(Call.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    calls = rows.scalars().all()

    items = [_call_list_item(call) for call in calls]

    return CallListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{execution_id}", response_model=CallDetail)
async def get_call(
    execution_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> CallDetail:
    call = await get_call_by_voice_id(session, tenant.client_id, execution_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found",
                    "message": f"No call with execution id '{execution_id}'."},
        )

    if call.status not in TERMINAL_STATUSES:
        try:
            payload = await voice_engine.get_execution(execution_id)
            if isinstance(payload, dict):
                call = await upsert_call_from_execution(
                    session, payload, client_id=tenant.client_id
                ) or call
        except VoiceEngineError:
            pass

    analysis_row = (await session.execute(
        select(CallAnalysis).where(CallAnalysis.call_id == call.id)
    )).scalar_one_or_none()

    from_number: str | None = None
    if call.batch_id is not None:
        await session.refresh(call, attribute_names=["batch"])
        from_number = call.batch.from_number if call.batch else None

    return CallDetail(
        call_id=call.voice_call_id,
        agent_id=call.agent_id,
        batch_id=call.batch_id,
        contact_number=call.contact_number,
        from_number=from_number,
        status=call.status,
        duration=call.duration,
        cost=call.cost,
        hangup_reason=call.hangup_reason,
        recording_url=call.recording_url,
        created_at=call.created_at.isoformat() if call.created_at else None,
        analysis=_analysis_result(analysis_row),
        transcript=call.transcript,
        extracted_data=call.extracted_data,
        patient_ref=call.patient_ref,
        retry_count=call.retry_count,
    )


@router.post("/{execution_id}/stop", response_model=StopCallResponse)
async def stop_call(
    execution_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    session: AsyncSession = Depends(get_session),
) -> StopCallResponse:
    call = await get_call_by_voice_id(session, tenant.client_id, execution_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found",
                    "message": f"No call with execution id '{execution_id}'."},
        )

    result = await voice_engine.stop_call(execution_id)
    response = StopCallResponse.model_validate(result)
    if response.status:
        call.status = response.status
    return response


@router.post("/{execution_id}/analyze", response_model=CallAnalysisResult)
async def analyze_call_endpoint(
    execution_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CallAnalysisResult:
    """Trigger or re-run LLM analysis on a call. Runs synchronously and returns the result."""
    call = await get_call_by_voice_id(session, tenant.client_id, execution_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found",
                    "message": f"No call with execution id '{execution_id}'."},
        )

    if not call.transcript:
        raise HTTPException(
            status_code=422,
            detail={"error": "no_transcript",
                    "message": "Call has no transcript — analysis is not possible."},
        )

    client_config = await get_config(session, tenant.client_id)
    analysis = await analyze_call(session, call, settings, client_config)
    if analysis is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "analysis_failed",
                    "message": "LLM analysis failed. Check API key configuration."},
        )

    result = CallAnalysisResult.from_model(analysis)
    assert result is not None  # analysis is non-None here
    return result
