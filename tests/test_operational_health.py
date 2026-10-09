"""
tests/test_operational_health.py
Tests for Phase 5E Operational Health & Lifecycle Readiness.

Validates:
- Liveness (/api/health/live) independence, speed, and unauthenticated access
- Readiness (/api/health/ready) semantics across standalone, connected, and degraded states
- Information-leak prevention on database connection failures (zero secret disclosure)
- Supported deterministic LLM fallback behavior (no unready state on missing API key)
- Scraper subprocess idle/busy tracking
- Legacy /api/status endpoint backwards compatibility
- Graceful server shutdown resource cleanup (database pool closure, subprocess termination)
"""

import os
import pytest
import httpx
from unittest.mock import MagicMock, patch

from api_server import app, shutdown_event
import api_server


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    """Async HTTP client targeting the FastAPI application."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


# ==============================================================================
# 1. Liveness Probe (/api/health/live) Tests
# ==============================================================================

@pytest.mark.anyio
async def test_liveness_probe_returns_200_and_status_alive(async_client):
    """Liveness probe must return 200 OK with alive status and uptime."""
    response = await async_client.get("/api/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0


@pytest.mark.anyio
async def test_liveness_probe_requires_no_authentication(async_client):
    """Liveness probe must be publicly accessible without API keys."""
    response = await async_client.get("/api/health/live")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_liveness_probe_independent_of_database(async_client, monkeypatch):
    """Liveness probe must never attempt to connect to PostgreSQL or check DB status."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid:creds@127.0.0.1:59999/dead")
    with patch.object(api_server.db_manager, "get_connection", side_effect=Exception("Should not be called")):
        response = await async_client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


# ==============================================================================
# 2. Readiness Probe (/api/health/ready) Tests
# ==============================================================================

@pytest.mark.anyio
async def test_readiness_standalone_mode_when_database_unconfigured(async_client, monkeypatch):
    """
    When DATABASE_URL and DB_* are unconfigured, application operates in standalone mode.
    Agent reasoning and audits remain supported; readiness must return 200 OK.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    response = await async_client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["mode"] == "standalone"
    assert data["components"]["database"]["status"] == "unconfigured"
    assert data["components"]["database"]["mode"] == "standalone"


@pytest.mark.anyio
async def test_readiness_connected_mode_success(async_client, monkeypatch):
    """When DATABASE_URL is configured and reachable, readiness returns 200 OK connected."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://valid_user:secret_pass@127.0.0.1:5432/test_db")

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_conn
    mock_cm.__exit__.return_value = None

    with patch.object(api_server.db_manager, "get_connection", return_value=mock_cm):
        response = await async_client.get("/api/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["mode"] == "connected"
        assert data["components"]["database"]["status"] == "connected"


@pytest.mark.anyio
async def test_readiness_connected_mode_database_failure_returns_503(async_client, monkeypatch):
    """
    When DATABASE_URL is configured but unreachable, readiness returns 503 Service Unavailable.
    Crucially, error response must NOT disclose passwords, URLs, or tracebacks.
    """
    secret_pass = "super_secret_db_password_123"
    db_url = f"postgresql://app_user:{secret_pass}@prod-db-internal.vpc:5432/primary"
    monkeypatch.setenv("DATABASE_URL", db_url)

    with patch.object(api_server.db_manager, "get_connection", side_effect=Exception(f"Connection timeout to {db_url}")):
        response = await async_client.get("/api/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["mode"] == "connected"
        assert data["components"]["database"]["status"] == "unavailable"
        assert data["components"]["database"]["message"] == "Configured database is unreachable."

        # Strictly verify zero credential or connection string leakage in response text
        raw_text = response.text
        assert secret_pass not in raw_text
        assert "prod-db-internal" not in raw_text
        assert "Connection timeout" not in raw_text


@pytest.mark.anyio
async def test_readiness_llm_status_with_and_without_api_key(async_client, monkeypatch):
    """
    Readiness verifies LLM configuration state without performing outbound network calls.
    Absence of GEMINI_API_KEY does NOT mark the service unready because deterministic fallback is supported.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)

    # 1. Configured mode
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey123")
    res_configured = await async_client.get("/api/health/ready")
    assert res_configured.status_code == 200
    llm_comp = res_configured.json()["components"]["llm"]
    assert llm_comp["status"] == "configured"
    assert llm_comp["provider"] == "gemini"

    # 2. Fallback mode (deterministic)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res_fallback = await async_client.get("/api/health/ready")
    assert res_fallback.status_code == 200
    llm_comp = res_fallback.json()["components"]["llm"]
    assert llm_comp["status"] == "fallback"
    assert llm_comp["provider"] == "deterministic"
    # Overall service status remains ready
    assert res_fallback.json()["status"] == "ready"


@pytest.mark.anyio
async def test_readiness_reports_scraper_state(async_client, monkeypatch):
    """Readiness reports whether the scraper background process is idle or busy."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)

    # Idle state
    with patch("api_server.is_scraper_running", return_value=False):
        res = await async_client.get("/api/health/ready")
        assert res.json()["components"]["scraper"]["status"] == "idle"

    # Busy state
    with patch("api_server.is_scraper_running", return_value=True):
        res = await async_client.get("/api/health/ready")
        assert res.json()["components"]["scraper"]["status"] == "busy"
        # Overall service is still ready to handle API calls
        assert res.json()["status"] == "ready"


# ==============================================================================
# 3. Backwards Compatibility for /api/status
# ==============================================================================

@pytest.mark.anyio
async def test_legacy_api_status_backwards_compatibility(async_client):
    """The legacy /api/status endpoint must preserve exact response contract."""
    response = await async_client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "is_running" in data
    assert "running_process" in data
    assert data["success"] is True
    assert isinstance(data["is_running"], bool)


# ==============================================================================
# 4. Graceful Lifecycle & Resource Cleanup Tests
# ==============================================================================

@pytest.mark.anyio
async def test_shutdown_closes_database_manager():
    """Server shutdown handler must safely close the database connection pool."""
    with patch.object(api_server.db_manager, "close") as mock_db_close:
        await shutdown_event()
        mock_db_close.assert_called_once()


@pytest.mark.anyio
async def test_shutdown_terminates_active_scraper_process():
    """Server shutdown handler must terminate and kill any active scraper subprocess."""
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # Process is still running
    mock_process.returncode = None

    api_server.running_process = mock_process
    try:
        with patch.object(api_server.db_manager, "close"):
            await shutdown_event()
            mock_process.terminate.assert_called_once()
            assert api_server.running_process is None
    finally:
        api_server.running_process = None


@pytest.mark.anyio
async def test_shutdown_idempotent_when_no_active_resources():
    """Server shutdown must complete safely and idempotently without raising errors."""
    api_server.running_process = None
    with patch.object(api_server.db_manager, "close") as mock_close:
        await shutdown_event()
        mock_close.assert_called_once()
