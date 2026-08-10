from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import TenantContext
from app.dependencies import get_current_tenant, get_sql_agent_settings
from app.main import create_app
from app.routers import sql_agent
from app.sql_agent.config import SqlAgentSettings
from app.sql_agent.schemas import BuildQueryResponse


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args) -> None:
        return None

    def add(self, _item) -> None:
        return None

    async def commit(self) -> None:
        return None


def test_sql_agent_router_returns_handled_status(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(sql_agent.router, prefix="/v1")

    app.dependency_overrides[get_current_tenant] = lambda: TenantContext(
        client_id=uuid4(),
        name="test",
        status="active",
    )
    app.dependency_overrides[get_sql_agent_settings] = lambda: SqlAgentSettings(
        sql_agent_explain_validation=False,
    )

    async def fake_build_query(*args, **kwargs) -> BuildQueryResponse:
        return BuildQueryResponse(
            status="built",
            sql="SELECT id FROM patients LIMIT 200",
            validated=True,
            tables_used=["patients"],
            confidence=0.9,
        )

    monkeypatch.setattr(sql_agent, "build_query", fake_build_query)

    response = TestClient(app).post(
        "/v1/sql-agent/query",
        json={"question": "List patients"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "built"
    assert response.json()["validated"] is True


def test_sql_agent_route_is_protected_by_api_key() -> None:
    response = TestClient(create_app()).post(
        "/v1/sql-agent/query",
        json={"question": "List patients"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_sql_agent_route_accepts_valid_api_key(monkeypatch) -> None:
    tenant = TenantContext(client_id=uuid4(), name="test", status="active")

    async def fake_resolve_api_key(_session, raw_key: str) -> TenantContext | None:
        assert raw_key == "tk_test"
        return tenant

    async def fake_build_query(*args, **kwargs) -> BuildQueryResponse:
        assert kwargs["audit_client_id"] == tenant.client_id
        return BuildQueryResponse(status="blocked", reason="write_intent")

    monkeypatch.setattr("app.middleware.resolve_api_key", fake_resolve_api_key)
    monkeypatch.setattr("app.db.session.get_session_factory", lambda: lambda: _FakeSession())
    monkeypatch.setattr(sql_agent, "build_query", fake_build_query)

    response = TestClient(create_app()).post(
        "/v1/sql-agent/query",
        headers={"X-API-Key": "tk_test"},
        json={"question": "Delete all patients"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


def test_calling_service_can_build_sql_through_endpoint(monkeypatch) -> None:
    tenant = TenantContext(client_id=uuid4(), name="calling-service", status="active")
    seen: dict[str, object] = {}

    async def fake_resolve_api_key(_session, raw_key: str) -> TenantContext | None:
        assert raw_key == "tk_service_key"
        return tenant

    async def fake_build_query(question, *, workspace, settings, audit_client_id):
        seen["question"] = question
        seen["workspace"] = workspace
        seen["audit_client_id"] = audit_client_id
        return BuildQueryResponse(
            status="built",
            sql="SELECT COUNT(*) AS patient_count FROM patients LIMIT 200",
            dialect="postgresql",
            validated=True,
            explanation="Counts patients.",
            tables_used=["patients"],
            confidence=0.92,
            critic_notes="The SQL answers the request.",
        )

    monkeypatch.setattr("app.middleware.resolve_api_key", fake_resolve_api_key)
    monkeypatch.setattr("app.db.session.get_session_factory", lambda: lambda: _FakeSession())
    monkeypatch.setattr(sql_agent, "build_query", fake_build_query)

    response = TestClient(create_app()).post(
        "/v1/sql-agent/query",
        headers={"X-API-Key": "tk_service_key"},
        json={
            "question": "How many patients registered last month?",
            "workspace": "kalaam",
        },
    )

    assert response.status_code == 200
    assert seen == {
        "question": "How many patients registered last month?",
        "workspace": "kalaam",
        "audit_client_id": tenant.client_id,
    }
    assert response.json() == {
        "status": "built",
        "sql": "SELECT COUNT(*) AS patient_count FROM patients LIMIT 200",
        "dialect": "postgresql",
        "validated": True,
        "explanation": "Counts patients.",
        "tables_used": ["patients"],
        "confidence": 0.92,
        "critic_notes": "The SQL answers the request.",
        "clarifying_question": None,
        "reason": None,
    }
