"""FastAPI dependencies — shared resources injected into route handlers."""

from fastapi import Request

from app.core.bolna_client import BolnaClient


def get_bolna_client(request: Request) -> BolnaClient:
    """Return the process-wide Bolna client created during app startup."""
    return request.app.state.bolna_client
