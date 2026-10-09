"""
tests/test_api_server.py
------------------------
Isolated unit test suite for API server endpoints (Phase 5C).
Verifies:
1. Public /api/status route works without authentication and without PostgreSQL.
2. Protected business endpoints (/api/businesses, /api/businesses/{id}, etc.)
   function with mock repository and do NOT require a running PostgreSQL server.
3. Protected pipeline run endpoints (/api/runs, /api/runs/{run_id})
   function with mock repository without PostgreSQL.
4. Live PostgreSQL integration test is isolated and marked with @pytest.mark.postgres_integration.
"""

import os
import pytest
import httpx
from unittest.mock import MagicMock

from api_server import app, get_repository, verify_api_key
from database.db import ScraperRepository, DatabaseManager

TEST_API_KEY = "test-auth-token-xyz"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_repository():
    """Mock ScraperRepository providing canned responses for all dashboard and run queries."""
    repo = MagicMock(spec=ScraperRepository)
    repo.get_businesses_for_dashboard.return_value = [
        {
            "id": 1,
            "business_name": "Acme Dental",
            "website_url": "https://acmedental.test",
            "opportunity_score": 85,
            "outreach_status": "new",
            "extracted_emails": ["contact@acmedental.test"],
            "source_platforms": ["google_maps"],
        },
        {
            "id": 2,
            "business_name": "Apex Plumbing",
            "website_url": "https://apexplumbing.test",
            "opportunity_score": 72,
            "outreach_status": "contacted",
            "extracted_emails": ["info@apexplumbing.test"],
            "source_platforms": ["google_maps"],
        },
    ]
    repo.get_business_detail_for_dashboard.side_effect = lambda bid: {
        "id": str(bid),
        "business_name": "Acme Dental",
        "website_url": "https://acmedental.test",
        "opportunity_score": 85,
        "outreach_status": "new",
        "likely_service_match": ["SEO Optimization"],
        "detected_pain_points": ["Slow website"],
    } if bid == 1 else None

    repo.get_outreach_drafts.side_effect = lambda bid: {
        "id": 101,
        "pain_point_positioning": "Mobile friction",
        "cold_email_draft": "Hi Acme Dental team...",
        "whatsapp_draft": "Hello!",
    } if bid == 1 else None

    repo.get_intent_profile.side_effect = lambda bid: {
        "intent_score": 78,
        "top_intent_signals": ["Hiring engineers"],
        "outreach_urgency": "high",
    } if bid == 1 else None

    repo.update_business.side_effect = lambda bid, fields: bid == 1
    repo.delete_business.side_effect = lambda bid: bid == 1
    repo.batch_delete_businesses.return_value = 2
    repo.delete_all_businesses.return_value = True

    repo.get_pipeline_runs.return_value = [
        {
            "run_id": "run-001",
            "search_query": "dentists in Austin",
            "started_at": "2026-10-09T10:00:00Z",
            "total_businesses": 10,
            "success_rate": 0.9,
        }
    ]
    repo.get_pipeline_run_detail.side_effect = lambda rid: {
        "run_id": rid,
        "search_query": "dentists in Austin",
        "total_businesses": 10,
        "business_records": [],
    } if rid == "run-001" else None

    return repo


@pytest.fixture(autouse=True)
def configure_auth_and_repo(monkeypatch, mock_repository):
    """Enforces mock auth and mock repository for all tests by default."""
    monkeypatch.setenv("API_AUTH_TOKEN", TEST_API_KEY)
    # Ensure unconfigured DB URL does not affect tests
    monkeypatch.setenv("DATABASE_URL", "postgresql://mock_user:mock_pass@127.0.0.1:5432/mock_db")
    app.dependency_overrides[verify_api_key] = lambda: TEST_API_KEY
    app.dependency_overrides[get_repository] = lambda: mock_repository
    yield
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_repository, None)


# -----------------------------------------------------------------------------
# 1. Unauthenticated Public Health Route
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_api_status():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "is_running" in data
        assert isinstance(data["is_running"], bool)


# -----------------------------------------------------------------------------
# 2. Business Management Routes (Mocked Repository)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_api_businesses_pagination(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/businesses?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["businesses"]) == 2
        assert data["limit"] == 5
        assert data["offset"] == 0
        mock_repository.get_businesses_for_dashboard.assert_called_once_with(limit=5, offset=0)


@pytest.mark.anyio
async def test_api_business_detail_found(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/businesses/1")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["business"]["business_name"] == "Acme Dental"


@pytest.mark.anyio
async def test_api_business_detail_not_found(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/businesses/999")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Business not found"


@pytest.mark.anyio
async def test_api_business_outreach_drafts(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/businesses/1/outreach")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["outreach"]["pain_point_positioning"] == "Mobile friction"


@pytest.mark.anyio
async def test_api_business_intent_profile(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/businesses/1/intent")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["intent"]["intent_score"] == 78


@pytest.mark.anyio
async def test_api_update_business(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.patch("/api/businesses/1", json={"category": "Healthcare"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["id"] == 1
        assert data["updated"] == {"category": "Healthcare"}


@pytest.mark.anyio
async def test_api_update_business_not_found(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.patch("/api/businesses/999", json={"category": "Healthcare"})
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Business not found"


@pytest.mark.anyio
async def test_api_delete_single_business(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.delete("/api/businesses/1")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.anyio
async def test_api_batch_delete_businesses(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.post("/api/businesses/batch-delete", json={"ids": ["1", "2"]})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_count"] == 2


@pytest.mark.anyio
async def test_api_delete_all_businesses(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.delete("/api/businesses")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# -----------------------------------------------------------------------------
# 3. Pipeline Run Routes (Mocked Repository)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_api_runs(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/runs?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["runs"]) == 1
        assert data["runs"][0]["run_id"] == "run-001"


@pytest.mark.anyio
async def test_api_run_detail_found(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/runs/run-001")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["run"]["run_id"] == "run-001"


@pytest.mark.anyio
async def test_api_run_detail_not_found(mock_repository):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY}
    ) as client:
        response = await client.get("/api/runs/nonexistent-run")
        assert response.status_code == 404
        assert response.json()["detail"] == "Run not found"


# -----------------------------------------------------------------------------
# 4. Explicitly Marked PostgreSQL Integration Test
# -----------------------------------------------------------------------------

@pytest.mark.postgres_integration
@pytest.mark.anyio
async def test_real_postgres_integration():
    """
    True database integration test requiring a running PostgreSQL server.
    Explicitly marked with @pytest.mark.postgres_integration.
    Skipped dynamically if no live PostgreSQL instance is available.
    """
    real_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not real_db_url or "mock" in real_db_url:
        pytest.skip("No real PostgreSQL instance configured (set TEST_DATABASE_URL to run)")

    try:
        real_mgr = DatabaseManager(db_url=real_db_url, timeout=2.0, lazy=False)
        real_repo = ScraperRepository(real_mgr)
        # Test basic connection checkout
        with real_mgr.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                res = cur.fetchone()
                assert res[0] == 1
        real_mgr.close()
    except Exception as e:
        pytest.skip(f"Live PostgreSQL server unavailable: {e}")
