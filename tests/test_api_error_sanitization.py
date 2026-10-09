"""
tests/test_api_error_sanitization.py
------------------------------------
Tests that API handlers do not leak sensitive database errors, credentials,
table names, connection strings, or raw exception strings to clients (Phase 5C).
"""

import pytest
import httpx
from unittest.mock import MagicMock
import psycopg2

from api_server import app, get_repository, verify_api_key
from database.db import (
    ScraperRepository,
    DatabaseConnectionError,
    DatabasePoolTimeoutError,
)

TEST_API_KEY = "test-auth-token-xyz"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_failing_repo():
    """Repository mock whose methods raise simulated raw/sensitive database errors."""
    repo = MagicMock(spec=ScraperRepository)
    repo.get_businesses_for_dashboard.side_effect = psycopg2.OperationalError(
        "FATAL: password authentication failed for user 'superadmin' at host 10.0.0.12:5432 with token abc_token_123"
    )
    repo.get_business_detail_for_dashboard.side_effect = DatabaseConnectionError(
        "Could not connect to database at postgresql://admin:secret_pass_999@internal.db:5432/main."
    )
    repo.get_outreach_drafts.side_effect = psycopg2.ProgrammingError(
        "relation 'secret_internal_salaries' does not exist at character 42"
    )
    repo.get_intent_profile.side_effect = DatabasePoolTimeoutError(
        "Database connection pool exhausted. Timed out after 10.0s (configured max 10 connections)."
    )
    repo.update_business.side_effect = psycopg2.DatabaseError(
        "deadlock detected on row lock table 'businesses' key (id)=(1) concurrent transaction 987654"
    )
    repo.delete_business.side_effect = Exception(
        "Unhandled internal crash in postgresql driver with trace /var/secrets/creds.pem"
    )
    repo.batch_delete_businesses.side_effect = psycopg2.OperationalError(
        "server closed the connection unexpectedly while executing DELETE FROM sensitive_db"
    )
    repo.delete_all_businesses.side_effect = psycopg2.OperationalError(
        "database 'production_data' is in recovery mode"
    )
    repo.get_pipeline_runs.side_effect = psycopg2.OperationalError(
        "FATAL: terminating connection due to administrator command user=app_user db=prod_cluster"
    )
    repo.get_pipeline_run_detail.side_effect = Exception(
        "disk I/O error on /dev/sda1 containing /var/lib/postgresql/data/base"
    )
    return repo


@pytest.fixture(autouse=True)
def configure_auth_and_failing_repo(monkeypatch, mock_failing_repo):
    monkeypatch.setenv("API_AUTH_TOKEN", TEST_API_KEY)
    app.dependency_overrides[verify_api_key] = lambda: TEST_API_KEY
    app.dependency_overrides[get_repository] = lambda: mock_failing_repo
    yield
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_repository, None)


@pytest.mark.anyio
async def test_get_businesses_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.get("/api/businesses")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while retrieving businesses."
        # Verify zero credential leakage
        assert "superadmin" not in resp.text
        assert "abc_token_123" not in resp.text
        assert "password" not in resp.text.lower()


@pytest.mark.anyio
async def test_get_business_detail_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.get("/api/businesses/1")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while retrieving business details."
        assert "secret_pass_999" not in resp.text
        assert "internal.db" not in resp.text


@pytest.mark.anyio
async def test_get_outreach_drafts_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.get("/api/businesses/1/outreach")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while retrieving outreach drafts."
        assert "secret_internal_salaries" not in resp.text


@pytest.mark.anyio
async def test_get_intent_profile_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.get("/api/businesses/1/intent")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while retrieving intent profile."


@pytest.mark.anyio
async def test_update_business_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.patch("/api/businesses/1", json={"category": "Dental"})
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while updating business."
        assert "deadlock" not in resp.text
        assert "987654" not in resp.text


@pytest.mark.anyio
async def test_delete_single_business_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.delete("/api/businesses/1")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while deleting business."
        assert "creds.pem" not in resp.text


@pytest.mark.anyio
async def test_batch_delete_businesses_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.post("/api/businesses/batch-delete", json={"ids": ["1", "2"]})
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while batch deleting businesses."
        assert "sensitive_db" not in resp.text


@pytest.mark.anyio
async def test_delete_all_businesses_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.delete("/api/businesses")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while clearing businesses."
        assert "production_data" not in resp.text


@pytest.mark.anyio
async def test_get_pipeline_runs_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.get("/api/runs")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while retrieving pipeline runs."
        assert "prod_cluster" not in resp.text


@pytest.mark.anyio
async def test_get_pipeline_run_detail_sanitizes_db_error():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}) as client:
        resp = await client.get("/api/runs/run-test")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal error occurred while retrieving run details."
        assert "/var/lib/postgresql" not in resp.text
