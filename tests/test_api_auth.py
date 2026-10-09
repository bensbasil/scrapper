"""
tests/test_api_auth.py
----------------------
Comprehensive regression tests for Phase 5B P0-1: API Authentication.
Verifies:
1. Fail closed when API_AUTH_TOKEN is not configured on the server (returns 401).
2. Missing X-API-Key returns 401.
3. Invalid X-API-Key returns 401.
4. Valid X-API-Key returns 200.
5. Alternative Authorization: Bearer token is supported.
6. Public health endpoint (/api/status) is accessible without credentials.
7. Protected endpoints reject unauthenticated requests across agent, scraping, business, and run domains.
8. Incoming secrets are not leaked in server logs.
"""

import os
import logging
import pytest
import httpx
from unittest.mock import MagicMock
from api_server import app, get_repository
from database.db import ScraperRepository


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def mock_repo_for_auth_tests():
    mock_repo = MagicMock(spec=ScraperRepository)
    mock_repo.get_businesses_for_dashboard.return_value = []
    app.dependency_overrides[get_repository] = lambda: mock_repo
    yield
    app.dependency_overrides.pop(get_repository, None)


@pytest.mark.anyio
async def test_fail_closed_when_token_not_configured(monkeypatch):
    """If API_AUTH_TOKEN is unset or empty, protected endpoints must fail closed with 401."""
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Request with a key provided, but server has no configured token
        resp = await client.get("/api/businesses", headers={"X-API-Key": "some-key"})
        assert resp.status_code == 401
        assert "server API authentication token is not configured" in resp.json()["detail"]

        # Empty token configured also fails closed
        monkeypatch.setenv("API_AUTH_TOKEN", "   ")
        resp2 = await client.get("/api/businesses", headers={"X-API-Key": "some-key"})
        assert resp2.status_code == 401
        assert "server API authentication token is not configured" in resp2.json()["detail"]


@pytest.mark.anyio
async def test_missing_api_key_rejected(monkeypatch):
    """When API_AUTH_TOKEN is set, requests without X-API-Key must be rejected with 401."""
    monkeypatch.setenv("API_AUTH_TOKEN", "production-secret-token-12345")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/businesses")
        assert resp.status_code == 401
        assert "missing api key" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_invalid_api_key_rejected(monkeypatch):
    """Invalid keys must be rejected with 401."""
    monkeypatch.setenv("API_AUTH_TOKEN", "production-secret-token-12345")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/businesses", headers={"X-API-Key": "wrong-token"})
        assert resp.status_code == 401
        assert "invalid api key" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_valid_api_key_accepted(monkeypatch):
    """Valid X-API-Key allows access to protected endpoints."""
    token = "production-secret-token-12345"
    monkeypatch.setenv("API_AUTH_TOKEN", token)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/businesses", headers={"X-API-Key": token})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_bearer_authorization_header_accepted(monkeypatch):
    """Clients sending Authorization: Bearer <token> are supported."""
    token = "production-secret-token-12345"
    monkeypatch.setenv("API_AUTH_TOKEN", token)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/businesses", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_public_status_endpoint_unauthenticated(monkeypatch):
    """The /api/status endpoint must remain unauthenticated for monitoring/heartbeats."""
    # Even when server token is unset
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_running" in data
        assert data["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint,method,payload", [
    ("/api/agent/run", "POST", {"goal": "Find plumbers in Chicago"}),
    ("/api/agent/execute", "POST", {"goal": "Find dentists in Austin"}),
    ("/api/agent/tasks/task-9999", "GET", None),
    ("/api/scrape", "POST", {"query": "lawyers", "city": "Dallas"}),
    ("/api/stop", "POST", None),
    ("/api/recrawl", "POST", None),
    ("/api/runs", "GET", None),
    ("/api/runs/test-run-123", "GET", None),
    ("/api/businesses", "GET", None),
    ("/api/businesses/1", "GET", None),
    ("/api/businesses/1", "DELETE", None),
    ("/api/businesses/1", "PATCH", {"outreach_status": "contacted"}),
])
async def test_all_protected_endpoints_reject_unauthenticated(monkeypatch, endpoint, method, payload):
    """Verifies that all sensitive, execution, and data endpoints fail closed without credentials."""
    monkeypatch.setenv("API_AUTH_TOKEN", "valid-secret-key")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        if method == "GET":
            resp = await client.get(endpoint)
        elif method == "POST":
            resp = await client.post(endpoint, json=payload or {})
        elif method == "DELETE":
            resp = await client.delete(endpoint)
        elif method == "PATCH":
            resp = await client.patch(endpoint, json=payload or {})

        assert resp.status_code == 401
        assert "missing api key" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_api_keys_are_not_logged(monkeypatch, caplog):
    """Ensure incoming API key values do not appear in any log outputs."""
    secret = "super-secret-unguessable-key-998877"
    monkeypatch.setenv("API_AUTH_TOKEN", secret)

    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            # Try valid request
            await client.get("/api/businesses", headers={"X-API-Key": secret})
            # Try invalid request
            await client.get("/api/businesses", headers={"X-API-Key": "attempted-bogus-key"})

    # Check that the secret was never recorded in logs
    assert secret not in caplog.text
    assert "attempted-bogus-key" not in caplog.text
