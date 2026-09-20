from __future__ import annotations

import math
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import TenantContext
from app.config import Settings, get_settings
from app.core.voice_engine import VoiceEngineClient, VoiceEngineError
from app.db.models import Call, CallAnalysis
from app.db.session import get_session
from app.dependencies import get_current_tenant, get_voice_engine
from app.schemas.analysis import (
    CallAnalysisResult,
    CallDetail,
    CallListItem,
    CallListResponse,
)
from app.schemas.calls import MakeCallRequest, MakeCallResponse, StopCallResponse
from app.services.analysis import analyze_call
from app.services.call_placement import place_call
from app.services.call_sync import complete_call, sync_execution
from app.services.store import (
    TERMINAL_STATUSES,
    get_call_by_voice_id,
)
from app.services.tenants import get_config

router = APIRouter(prefix="/calls", tags=["calls"])


def _analysis_result(analysis: CallAnalysis | None) -> CallAnalysisResult | None:
    return CallAnalysisResult.from_model(analysis)


def _call_list_item(call: Call) -> CallListItem:
    return CallListItem(
        call_id=call.voice_call_id,
        agent_id=call.agent_id,
        batch_id=call.batch_id,
        contact_number=call.contact_number,
        from_number=call.from_number
        or (call.batch.from_number if call.batch else None),
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
    return await place_call(
        session,
        client_id=tenant.client_id,
        body=body,
        voice_engine=voice_engine,
        settings=settings,
        validate=validate,
    )


@router.get("", response_model=CallListResponse)
async def list_calls(
    agent_id: str | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    call_outcome: str | None = Query(
        default=None, description="Granular call outcome, e.g. 'scheduled_booking'."
    ),
    disposition_status: str | None = Query(
        default=None, description="Disposition status, e.g. 'Follow Up'."
    ),
    urgency: str | None = Query(default=None),
    q: str | None = Query(
        default=None, description="Substring search on contact number."
    ),
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
    if call_outcome:
        filters.append(CallAnalysis.call_outcome == call_outcome)
    if disposition_status:
        filters.append(CallAnalysis.disposition_status == disposition_status)
    if urgency:
        filters.append(CallAnalysis.urgency == urgency)
    if q:
        filters.append(Call.contact_number.ilike(f"%{q}%"))
    if date_from:
        filters.append(Call.created_at >= date_from)
    if date_to:
        filters.append(Call.created_at <= date_to)

    needs_analysis_join = bool(call_outcome or disposition_status or urgency)

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
        page_query.where(*filters)
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
    background_tasks: BackgroundTasks,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> CallDetail:
    call = await get_call_by_voice_id(session, tenant.client_id, execution_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"No call with execution id '{execution_id}'.",
            },
        )

    if call.status not in TERMINAL_STATUSES:
        try:
            payload = await voice_engine.get_execution(execution_id)
            if isinstance(payload, dict):
                synced_call, just_finished = await sync_execution(
                    session, payload, client_id=tenant.client_id
                )
                call = synced_call or call
                if just_finished:
                    await session.commit()
                    background_tasks.add_task(complete_call, call.id, settings)
        except VoiceEngineError:
            pass

    analysis_row = (
        await session.execute(
            select(CallAnalysis).where(CallAnalysis.call_id == call.id)
        )
    ).scalar_one_or_none()

    from_number = call.from_number
    if from_number is None and call.batch_id is not None:
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
    background_tasks: BackgroundTasks,
    tenant: TenantContext = Depends(get_current_tenant),
    voice_engine: VoiceEngineClient = Depends(get_voice_engine),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> StopCallResponse:
    call = await get_call_by_voice_id(session, tenant.client_id, execution_id)
    if call is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"No call with execution id '{execution_id}'.",
            },
        )

    result = await voice_engine.stop_call(execution_id)
    response = StopCallResponse.model_validate(result)
    if response.status:
        was_open = call.status not in TERMINAL_STATUSES
        call.status = response.status
        if was_open and call.status in TERMINAL_STATUSES:
            await session.commit()
            background_tasks.add_task(complete_call, call.id, settings)
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
            detail={
                "error": "not_found",
                "message": f"No call with execution id '{execution_id}'.",
            },
        )

    if not call.transcript:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_transcript",
                "message": "Call has no transcript — analysis is not possible.",
            },
        )

    client_config = await get_config(session, tenant.client_id)
    analysis = await analyze_call(session, call, settings, client_config)
    if analysis is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "analysis_failed",
                "message": "LLM analysis failed. Check API key configuration.",
            },
        )

    result = CallAnalysisResult.from_model(analysis)
    assert result is not None  # analysis is non-None here
    return result
