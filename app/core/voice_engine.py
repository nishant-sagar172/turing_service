"""Thin async client for the upstream voice engine (currently Bolna).

Wraps a single shared ``httpx.AsyncClient`` configured with the base URL and
Bearer auth. Engine-specific endpoints are added as methods; a generic
``request`` helper backs them and can be reused for endpoints we haven't
wrapped yet.

Docs: https://www.bolna.ai/docs — auth is ``Authorization: Bearer <API_KEY>``.
Content type is set per-request by httpx: ``application/json`` when ``json=``
is passed, ``multipart/form-data`` when ``files=``/``data=`` are passed.
"""

from __future__ import annotations

import asyncio
import json as jsonlib
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Transient-transport retry budget. Applied to idempotent requests only; see
# ``VoiceEngineClient.request``.
_MAX_TRANSPORT_ATTEMPTS = 3
_RETRY_BACKOFF_S = 0.5


def _form_value(value: Any) -> str:
    """Render a payload value for a multipart form part.

    A blanket ``str()`` is wrong here: ``str(True)`` is ``"True"``, which a
    case-sensitive boolean parser upstream will not read as true, and
    ``str({...})`` is a Python repr rather than JSON.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return jsonlib.dumps(value)
    return str(value)


class VoiceEngineError(Exception):
    """Raised when the voice engine returns a non-2xx response or is unreachable.

    ``status_code`` is the upstream HTTP status (None on transport failure).
    ``payload`` is the parsed upstream error body when available.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class VoiceEngineClient:
    """Async wrapper around the upstream voice engine's REST API."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        # NOTE: no default Content-Type — httpx picks JSON vs multipart per call.
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """Perform an authenticated request and return the parsed JSON body.

        Raises:
            VoiceEngineError: on transport failure or a non-2xx response.
        """
        # Retry transient transport failures for idempotent requests only. A
        # received non-2xx is never retried (it is a real application error),
        # and non-GET verbs are never retried because a duplicate POST could
        # place a second patient call or create a second batch.
        attempts = _MAX_TRANSPORT_ATTEMPTS if method.upper() == "GET" else 1

        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                )
            except httpx.RequestError as exc:  # DNS, connection, timeout, etc.
                if attempt + 1 >= attempts:
                    raise VoiceEngineError(
                        f"Failed to reach voice engine at {self._base_url}{path}: {exc}"
                    ) from exc
                await asyncio.sleep(_RETRY_BACKOFF_S * (2**attempt))
                continue

            if response.is_error:
                error_payload = _safe_json(response)
                log.error(
                    "voice engine error: %s %s → %s | body: %s",
                    method,
                    path,
                    response.status_code,
                    error_payload,
                )
                raise VoiceEngineError(
                    f"Voice engine returned {response.status_code} for {method} {path}",
                    status_code=response.status_code,
                    payload=error_payload,
                )

            return _safe_json(response)

        raise VoiceEngineError(
            f"Failed to reach voice engine at {self._base_url}{path}: retries exhausted"
        )

    async def get_user(self) -> Any:
        """GET /user/me — account info. Used as the connectivity probe."""
        return await self.request("GET", "/user/me")

    async def list_agents(self) -> Any:
        """GET /v2/agent/all — list all agents on the account."""
        return await self.request("GET", "/v2/agent/all")

    async def get_agent(self, agent_id: str) -> Any:
        """GET /v2/agent/{agent_id} — full agent config (read-only introspection)."""
        return await self.request("GET", f"/v2/agent/{agent_id}")

    async def list_phone_numbers(self) -> Any:
        """GET /phone-numbers/all — numbers owned on the account (caller IDs)."""
        return await self.request("GET", "/phone-numbers/all")

    async def make_call(self, payload: dict[str, Any]) -> Any:
        """POST /call — start (or schedule) a single outbound call."""
        return await self.request("POST", "/call", json=payload)

    async def stop_call(self, execution_id: str) -> Any:
        """POST /call/{execution_id}/stop — cancel a queued/scheduled call."""
        return await self.request("POST", f"/call/{execution_id}/stop")

    async def get_execution(self, execution_id: str) -> Any:
        """GET /executions/{execution_id} — status/transcript/outcome of a call."""
        return await self.request("GET", f"/executions/{execution_id}")

    async def create_batch(
        self,
        *,
        agent_id: str,
        csv_bytes: bytes,
        file_name: str = "recipients.csv",
        from_phone_numbers: list[str] | None = None,
        retry_config: str | None = None,
        webhook_url: str | None = None,
    ) -> Any:
        """POST /batches — create a batch by uploading a CSV (multipart).

        ``from_phone_numbers`` must be sent as one repeated form field per
        number (``--form 'from_phone_numbers="+91..."'`` per Bolna's own
        docs) — a single JSON-array-encoded field is read back literally as
        one malformed number and rejected. ``retry_config`` is a JSON-encoded
        string (multipart form fields carry strings).
        """
        data: dict[str, Any] = {"agent_id": agent_id}
        if from_phone_numbers:
            data["from_phone_numbers"] = from_phone_numbers
        if retry_config is not None:
            data["retry_config"] = retry_config
        if webhook_url is not None:
            data["webhook_url"] = webhook_url
        files = {"file": (file_name, csv_bytes, "text/csv")}
        return await self.request("POST", "/batches", data=data, files=files)

    async def schedule_batch(self, batch_id: str, payload: dict[str, Any]) -> Any:
        """POST /batches/{batch_id}/schedule — schedule a created batch.

        The engine's schedule endpoint expects multipart/form-data (NOT JSON),
        same as create. Each field is sent as a form part via
        ``files={k:(None,v)}``.
        """
        form = {k: (None, _form_value(v)) for k, v in payload.items()}
        log.info("schedule_batch: batch_id=%s payload=%s", batch_id, payload)
        return await self.request(
            "POST",
            f"/batches/{batch_id}/schedule",
            files=form,
        )

    async def list_agent_batches(self, agent_id: str) -> Any:
        """GET /batches/{agent_id}/all — all batches for an agent."""
        return await self.request("GET", f"/batches/{agent_id}/all")

    async def get_batch(self, batch_id: str) -> Any:
        """GET /batches/{batch_id} — batch status/details."""
        return await self.request("GET", f"/batches/{batch_id}")

    async def get_batch_executions(self, batch_id: str) -> Any:
        """GET /batches/{batch_id}/executions — per-call results in a batch."""
        return await self.request("GET", f"/batches/{batch_id}/executions")

    async def stop_batch(self, batch_id: str) -> Any:
        """POST /batches/{batch_id}/stop — halt a queued/running batch."""
        return await self.request("POST", f"/batches/{batch_id}/stop")

    async def delete_batch(self, batch_id: str) -> Any:
        """DELETE /batches/{batch_id} — remove a batch."""
        return await self.request("DELETE", f"/batches/{batch_id}")


def _safe_json(response: httpx.Response) -> Any:
    """Return parsed JSON, or the raw text wrapped in a dict if not JSON."""
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}
