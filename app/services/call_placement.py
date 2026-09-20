"""Places a single outbound call and records it.

Shared by the tenant route (``POST /v1/calls``, authenticated by X-API-Key) and
the operator route (``POST /v1/admin/clients/{client_id}/calls``, authenticated
by X-Admin-Key). Both need identical behaviour — agent gating, variable
validation, caller-ID resolution, and the ``calls`` row — so the orchestration
lives here rather than being duplicated per router.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.voice_engine import VoiceEngineClient
from app.schemas.calls import MakeCallRequest, MakeCallResponse
from app.services import agent_sync
from app.services.store import record_call
from app.services.tenants import get_config
from app.services.variables import check, resolve_variables


async def place_call(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    body: MakeCallRequest,
    voice_engine: VoiceEngineClient,
    settings: Settings,
    validate: bool | None = None,
) -> MakeCallResponse:
    """Validate, dispatch to the voice engine, and persist the call row."""
    if not await agent_sync.is_agent_enabled(session, client_id, body.agent_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "agent_not_enabled",
                "message": f"Agent '{body.agent_id}' is not enabled for this client.",
            },
        )

    warnings: list[str] = []
    do_validate = settings.validate_agent_variables if validate is None else validate
    if do_validate and body.user_data:
        contract = await resolve_variables(
            voice_engine,
            body.agent_id,
            settings,
            session=session,
            client_id=client_id,
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

    # body → client config → global settings
    from_phone_number = body.from_phone_number
    if from_phone_number is None:
        config = await get_config(session, client_id)
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
        user_data = body.user_data or {}
        patient_uhid = user_data.get("patient_uhid")
        client_ref = user_data.get("client_ref")
        await record_call(
            session,
            client_id=client_id,
            agent_id=body.agent_id,
            voice_call_id=response.execution_id,
            contact_number=body.recipient_phone_number,
            status=response.status or "queued",
            from_number=from_phone_number,
            workflow_code=body.workflow_code,
            patient_ref=str(patient_uhid) if patient_uhid is not None else None,
            client_ref=str(client_ref) if client_ref is not None else None,
        )

    return response
