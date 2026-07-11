"""/v1/calls — single outbound calls: trigger, track, stop.

Each call is validated against the selected agent's variable contract, placed
via Bolna, and persisted in turing's own DB. Reads serve from the DB and
refresh non-terminal calls from Bolna (this doubles as the reconcile path).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.bolna_client import BolnaClient, BolnaError
from app.db.session import get_session
from app.dependencies import get_bolna_client
from app.schemas.calls import (
    ExecutionResponse,
    MakeCallRequest,
    MakeCallResponse,
    StopCallResponse,
)
from app.services.store import (
    get_call_by_execution_id,
    record_single_call,
    upsert_call_from_execution,
)
from app.services.variables import check, resolve_variables

router = APIRouter(prefix="/calls", tags=["calls"])

_TERMINAL_STATUSES = {
    "completed", "no-answer", "busy", "failed", "canceled", "cancelled",
    "stopped", "error", "balance-low",
}


@router.post("", response_model=MakeCallResponse, status_code=200)
async def make_call(
    request: Request,
    body: MakeCallRequest,
    validate: bool | None = None,
    client: BolnaClient = Depends(get_bolna_client),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> MakeCallResponse:
    """Start a single outbound call now, or schedule it via ``scheduled_at``.

    If the request omits ``from_phone_number``, the service's configured
    default (``BOLNA_DEFAULT_FROM_NUMBER``) is used when set.

    Unless disabled, the agent's required variables are validated: a missing
    one rejects the call (422); extra variables are returned as warnings.
    """
    if body.from_phone_number is None:
        body.from_phone_number = settings.bolna_default_from_number

    warnings: list[str] = []
    do_validate = settings.validate_agent_variables if validate is None else validate
    if do_validate:
        contract = await resolve_variables(client, body.agent_id, settings)
        provided = set((body.user_data or {}).keys())
        missing, extra = check(provided, contract)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_required_variables",
                    "agent_id": body.agent_id,
                    "missing": missing,
                    "required": contract["required"],
                    "optional": contract["optional"],
                },
            )
        warnings = [
            f"variable '{name}' was sent but the agent's prompt does not use it"
            for name in extra
        ]

    result = await client.make_call(body.to_bolna_payload())
    response = MakeCallResponse.model_validate(result)
    response.warnings = warnings

    await record_single_call(
        session,
        client=getattr(request.state, "api_client", None),
        agent_id=body.agent_id,
        contact_number=body.recipient_phone_number,
        patient_ref=(body.user_data or {}).get("patient_uhid"),
        bolna_execution_id=response.execution_id,
        status=response.status,
    )
    return response


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_call(
    execution_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    """Fetch a call's status/transcript/outcome.

    Served from turing's DB; non-terminal (or unknown) calls are refreshed from
    Bolna first and the refreshed state is persisted.
    """
    call = await get_call_by_execution_id(session, execution_id)

    if call is None or call.status not in _TERMINAL_STATUSES:
        try:
            payload = await client.get_execution(execution_id)
            if isinstance(payload, dict):
                call = await upsert_call_from_execution(session, payload) or call
        except BolnaError:
            if call is None:
                raise  # unknown here AND upstream -> surface upstream error

    if call is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found",
                    "message": f"No call with execution id '{execution_id}'."},
        )

    return ExecutionResponse.model_validate(
        {
            "id": call.bolna_execution_id,
            "agent_id": call.agent_id,
            "status": call.status,
            "conversation_duration": call.duration,
            "total_cost": call.cost,
            "transcript": call.transcript,
            "extracted_data": call.extracted_data,
            "telephony_data": (call.raw_payload or {}).get("telephony_data"),
            "error_message": (call.raw_payload or {}).get("error_message"),
            "contact_number": call.contact_number,
            "patient_ref": call.patient_ref,
            "recording_url": call.recording_url,
            "hangup_reason": call.hangup_reason,
        }
    )


@router.post("/{execution_id}/stop", response_model=StopCallResponse)
async def stop_call(
    execution_id: str,
    client: BolnaClient = Depends(get_bolna_client),
    session: AsyncSession = Depends(get_session),
) -> StopCallResponse:
    """Cancel a queued or scheduled call before it executes."""
    result = await client.stop_call(execution_id)
    response = StopCallResponse.model_validate(result)

    call = await get_call_by_execution_id(session, execution_id)
    if call is not None and response.status:
        call.status = response.status
    return response
