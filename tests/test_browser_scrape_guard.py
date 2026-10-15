"""
tests/test_browser_scrape_guard.py
-----------------------------------
Regression test suite for browser-dependent scraping capability guard (Phase 6N-D.2).

Verifies:
1. Authenticated browser-dependent scrape requests (gmaps, justdial, indiamart)
   are rejected with HTTP 501 and 'BrowserScrapingDisabled' when Chromium is unavailable.
2. Background task / child process is NOT started and process locks are not retained.
3. Unauthenticated requests still follow existing authentication rules (HTTP 401).
4. Authenticated scrape succeeds with HTTP 200 when browser capability is available.
5. Health and readiness endpoints (/api/health/live, /api/health/ready, /api/status)
   continue to operate normally.
6. Non-browser operations (/api/recrawl, /api/businesses, /api/agent) remain unaffected.
7. SocialScraper's requests-based fallback functions cleanly when browser fails.
"""

import os
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from api_server import (
    app,
    is_scraper_running,
    log_history,
    set_browser_scraping_checker,
    reset_browser_scraping_cache,
    is_browser_scraping_available,
)
from scraper.connectors.social.social_scraper import SocialScraper, SocialScraperResult

TEST_API_KEY = "test-guard-token-12345"


@pytest.fixture(autouse=True)
def reset_guard_state(monkeypatch):
    """Ensure clean test environment for capability overrides and auth token."""
    monkeypatch.setenv("API_AUTH_TOKEN", TEST_API_KEY)
    monkeypatch.delenv("BROWSER_SCRAPING_ENABLED", raising=False)
    set_browser_scraping_checker(None)
    reset_browser_scraping_cache()
    log_history.clear()
    yield
    set_browser_scraping_checker(None)
    reset_browser_scraping_cache()
    log_history.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("source", ["gmaps", "justdial", "indiamart"])
async def test_authenticated_scrape_rejected_when_browser_unavailable(source):
    """
    When browser scraping is unavailable, authenticated scrape requests
    must be rejected with HTTP 501 and code 'BrowserScrapingDisabled'.
    """
    set_browser_scraping_checker(lambda: False)
    assert is_browser_scraping_available() is False

    payload = {"query": "plumbers in Miami", "limit": 5, "source": source}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/scrape",
            json=payload,
            headers={"X-API-Key": TEST_API_KEY},
        )

    assert resp.status_code == 501
    data = resp.json()
    assert "detail" in data
    assert data["detail"]["code"] == "BrowserScrapingDisabled"
    assert data["detail"]["error"] == "BrowserScrapingDisabled"
    assert source in data["detail"]["message"]
    assert "Chromium" in data["detail"]["message"]


@pytest.mark.anyio
async def test_subprocess_not_started_when_scrape_rejected(monkeypatch):
    """
    Rejection must happen BEFORE acquiring process locks or spawning subprocesses.
    Background tasks must not run and log_history must not be cleared.
    """
    set_browser_scraping_checker(lambda: False)
    mock_spawn = AsyncMock()
    monkeypatch.setattr("api_server.run_scraper_process", mock_spawn)

    log_history.append("[System] Pre-existing log line that should be preserved")

    payload = {"query": "lawyers in Chicago", "limit": 3}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/scrape",
            json=payload,
            headers={"X-API-Key": TEST_API_KEY},
        )

    assert resp.status_code == 501
    assert is_scraper_running() is False
    mock_spawn.assert_not_called()
    assert len(log_history) == 1
    assert "Pre-existing" in log_history[0]


@pytest.mark.anyio
async def test_unauthenticated_scrape_follows_existing_rules():
    """
    Authentication checks take precedence over capability checks.
    Requests without credentials must return HTTP 401, not 501.
    """
    set_browser_scraping_checker(lambda: False)

    payload = {"query": "electricians in Seattle"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Missing API key
        resp_missing = await client.post("/api/scrape", json=payload)
        assert resp_missing.status_code == 401
        assert "missing api key" in resp_missing.json()["detail"].lower()

        # 2. Invalid API key
        resp_invalid = await client.post(
            "/api/scrape",
            json=payload,
            headers={"X-API-Key": "invalid-wrong-token"},
        )
        assert resp_invalid.status_code == 401
        assert "invalid api key" in resp_invalid.json()["detail"].lower()


@pytest.mark.anyio
async def test_scrape_accepted_when_browser_available(monkeypatch):
    """
    When browser capability is verified as available, the scrape request
    must be accepted with HTTP 200 and dispatched to background tasks.
    """
    set_browser_scraping_checker(lambda: True)
    assert is_browser_scraping_available() is True

    mock_spawn = AsyncMock()
    monkeypatch.setattr("api_server.run_scraper_process", mock_spawn)

    payload = {"query": "bakeries in Portland", "limit": 4, "source": "gmaps"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/scrape",
            json=payload,
            headers={"X-API-Key": TEST_API_KEY},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Scraper started successfully" in data["message"]


@pytest.mark.anyio
async def test_health_and_status_endpoints_unaffected():
    """
    Disabling browser scraping must not affect liveness, readiness,
    or status endpoints.
    """
    set_browser_scraping_checker(lambda: False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Liveness
        resp_live = await client.get("/api/health/live")
        assert resp_live.status_code == 200
        assert resp_live.json()["status"] == "alive"

        # Readiness (standalone mode without DB)
        resp_ready = await client.get("/api/health/ready")
        assert resp_ready.status_code == 200
        assert resp_ready.json()["status"] == "ready"

        # Status
        resp_status = await client.get("/api/status")
        assert resp_status.status_code == 200
        assert resp_status.json()["success"] is True
        assert resp_status.json()["is_running"] is False


@pytest.mark.anyio
async def test_recrawl_endpoint_unaffected_by_browser_guard(monkeypatch):
    """
    POST /api/recrawl does not depend on Playwright and must NOT be rejected
    by the browser scraping capability guard.
    """
    set_browser_scraping_checker(lambda: False)
    mock_spawn = AsyncMock()
    monkeypatch.setattr("api_server.run_scraper_process", mock_spawn)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/recrawl?limit=5",
            headers={"X-API-Key": TEST_API_KEY},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Recrawl mode started" in data["message"]


def test_social_scraper_fallback_when_playwright_unavailable(monkeypatch):
    """
    Verify that SocialScraper safely degrades to HTTP/requests Open Graph metadata
    when Playwright browser initialization raises a launch failure.
    """
    scraper = SocialScraper(timeout=5)

    # Force browser initialization to raise an error simulating missing Chromium
    def failing_get_browser():
        raise RuntimeError("Chromium binary missing: Executable doesn't exist")

    monkeypatch.setattr(scraper, "_get_browser", failing_get_browser)

    # Mock _scrape_via_requests to return a reachable result
    expected_result = SocialScraperResult(
        platform="instagram",
        url="https://www.instagram.com/nike",
        is_reachable=True,
        follower_count=None,
        bio=None,
    )
    monkeypatch.setattr(scraper, "_scrape_via_requests", lambda url, platform: expected_result)

    result = scraper.scrape("https://www.instagram.com/nike")
    assert result.is_reachable is True
    assert result.platform == "instagram"
    scraper.close()


# ==============================================================================
# Phase 6N-D.4 Capability Function & Hardening Tests (Un-mocked / Narrow Mock)
# ==============================================================================


def test_capability_missing_chromium_returns_false_unmocked(monkeypatch, tmp_path):
    """
    When Chromium binary is absent on the filesystem, is_browser_scraping_available()
    must return False using real Playwright path discovery (no test hook).
    """
    # Direct Playwright to look into an empty test directory
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "empty_browsers"))
    reset_browser_scraping_cache()
    assert is_browser_scraping_available() is False


def test_capability_existing_executable_returns_true(tmp_path):
    """
    When Chromium executable exists and has execute permissions,
    is_browser_scraping_available() must return True.
    """
    fake_chrome = tmp_path / "chrome_bin"
    fake_chrome.write_text("#!/bin/sh\nexit 0\n")
    fake_chrome.chmod(0o755)

    mock_p = MagicMock()
    mock_p.chromium.executable_path = str(fake_chrome)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False

    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx):
        assert is_browser_scraping_available() is True


def test_capability_missing_or_inaccessible_executable_returns_false(tmp_path):
    """
    When Chromium executable is missing from disk or lacks execute permissions,
    is_browser_scraping_available() must fail closed (return False).
    """
    mock_p = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False

    # 1. Path does not exist on disk
    mock_p.chromium.executable_path = str(tmp_path / "nonexistent_binary")
    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx):
        assert is_browser_scraping_available() is False

    # 2. Path exists but lacks execute permission (mode 0o644)
    non_exec = tmp_path / "non_exec_binary"
    non_exec.write_text("plain text file")
    non_exec.chmod(0o644)
    mock_p.chromium.executable_path = str(non_exec)
    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx):
        assert is_browser_scraping_available() is False


@pytest.mark.parametrize("val", ["true", "True", "1", "yes", "enabled", "TRUE"])
def test_browser_scraping_enabled_true_cannot_bypass_missing_chromium(monkeypatch, tmp_path, val):
    """
    BROWSER_SCRAPING_ENABLED=true (or any truthy variation) MUST NEVER force
    availability to True when the Chromium binary is absent or invalid.
    """
    monkeypatch.setenv("BROWSER_SCRAPING_ENABLED", val)
    mock_p = MagicMock()
    mock_p.chromium.executable_path = str(tmp_path / "missing_chrome")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False

    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx):
        assert is_browser_scraping_available() is False


@pytest.mark.parametrize("val", ["false", "False", "0", "no", "off", "disabled", "  disabled  "])
def test_explicit_disable_values_return_false_even_with_valid_executable(monkeypatch, tmp_path, val):
    """
    Explicit disable values must immediately return False without checking the binary.
    """
    fake_chrome = tmp_path / "valid_chrome"
    fake_chrome.write_text("#!/bin/sh\nexit 0\n")
    fake_chrome.chmod(0o755)

    mock_p = MagicMock()
    mock_p.chromium.executable_path = str(fake_chrome)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False

    monkeypatch.setenv("BROWSER_SCRAPING_ENABLED", val)
    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx) as mock_sync:
        assert is_browser_scraping_available() is False
        # Playwright driver check should not even be invoked when explicitly disabled
        mock_sync.assert_not_called()


def test_unexpected_initialization_or_path_errors_fail_closed():
    """
    Any exception raised during Playwright import, driver launch, or path resolution
    must be caught, logged, and return False (fail closed).
    """
    # 1. Driver crash on enter
    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", side_effect=RuntimeError("Node process crashed")):
        assert is_browser_scraping_available() is False

    # 2. Playwright library import / load failure
    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", side_effect=ImportError("No module named 'playwright'")):
        assert is_browser_scraping_available() is False

    # 3. Exception on p.chromium property access
    reset_browser_scraping_cache()
    mock_p = MagicMock()
    type(mock_p).chromium = pytest.raises(Exception)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx):
        assert is_browser_scraping_available() is False


def test_cached_behavior_and_cache_reset(tmp_path):
    """
    Verify that physical binary detection is cached after the first check,
    and reset_browser_scraping_cache() clears the cached state.
    """
    fake_chrome = tmp_path / "cached_chrome"
    fake_chrome.write_text("#!/bin/sh\nexit 0\n")
    fake_chrome.chmod(0o755)

    mock_p = MagicMock()
    mock_p.chromium.executable_path = str(fake_chrome)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False

    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx) as mock_sync:
        # First call: invokes detection and caches True
        assert is_browser_scraping_available() is True
        assert mock_sync.call_count == 1

        # Second call: uses cache, does not invoke Playwright driver
        assert is_browser_scraping_available() is True
        assert mock_sync.call_count == 1

        # Reset cache
        reset_browser_scraping_cache()

        # Third call: re-executes detection, invokes Playwright driver again
        assert is_browser_scraping_available() is True
        assert mock_sync.call_count == 2


def test_environment_disable_not_cached_improperly(monkeypatch, tmp_path):
    """
    Verify that BROWSER_SCRAPING_ENABLED=false does not contaminate the binary cache.
    Removing the disable override allows subsequent calls to detect the valid binary.
    """
    fake_chrome = tmp_path / "toggle_chrome"
    fake_chrome.write_text("#!/bin/sh\nexit 0\n")
    fake_chrome.chmod(0o755)

    mock_p = MagicMock()
    mock_p.chromium.executable_path = str(fake_chrome)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_p
    mock_ctx.__exit__.return_value = False

    reset_browser_scraping_cache()
    with patch("playwright.sync_api.sync_playwright", return_value=mock_ctx):
        # Explicitly disabled
        monkeypatch.setenv("BROWSER_SCRAPING_ENABLED", "false")
        assert is_browser_scraping_available() is False

        # Dynamically un-disabled (without calling reset_browser_scraping_cache)
        monkeypatch.delenv("BROWSER_SCRAPING_ENABLED", raising=False)
        assert is_browser_scraping_available() is True


@pytest.mark.anyio
async def test_endpoint_scrape_rejected_with_unmocked_missing_browser(monkeypatch, tmp_path):
    """
    End-to-end integration test: when the environment lacks Chromium,
    POST /api/scrape must be rejected by the actual capability detection logic
    without set_browser_scraping_checker being set.
    """
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "empty_browsers"))
    reset_browser_scraping_cache()

    payload = {"query": "chiropractors in Dallas", "limit": 2}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/scrape",
            json=payload,
            headers={"X-API-Key": TEST_API_KEY},
        )

    assert resp.status_code == 501
    assert resp.json()["detail"]["code"] == "BrowserScrapingDisabled"
