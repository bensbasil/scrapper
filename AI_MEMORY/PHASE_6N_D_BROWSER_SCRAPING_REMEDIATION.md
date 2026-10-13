# Phase 6N-D.2: Browser-Dependent Scraping Capability Guard Remediation Report

**Project:** Business Opportunity Intelligence Platform  
**Repository:** `scrapper`  
**Date:** 2026-10-13  
**Auditor / Implementer:** Principal Enterprise Solutions & Systems Architect  
**Baseline Commit:** `0c61d28` (*fix(ci): separate frontend unit and container smoke tests*)  
**Investigation Reference:** [`AI_MEMORY/PHASE_6N_D_BROWSER_SCRAPING_INVESTIGATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6N_D_BROWSER_SCRAPING_INVESTIGATION.md)  
**Remediation Scope:** Implement deterministic capability guard for browser-dependent scraping (`POST /api/scrape`), reject unsupported in-container requests with HTTP 501 `BrowserScrapingDisabled`, preserve recrawl and core intelligence, and establish regression test coverage.

---

## 1. Executive Summary

During the Phase 6N-C Production Readiness Audit (Finding P0-1) and Phase 6N-D.1 Investigation, forensic analysis proved that while the backend Docker image installs `playwright==1.42.0`, it omits system Chromium binaries and desktop shared libraries (`playwright install --with-deps chromium`). Calling `POST /api/scrape` in a container returned a misleading HTTP `200 OK`, followed by an asynchronous background crash in `pipeline_runner.py` with `playwright._impl._errors.Error: Executable doesn't exist`.

In Phase 6N-D.2, we implemented **Option A (Deterministic Capability Guard)**:
- Rejects browser-dependent scraping requests **before** acquiring process locks or spawning background tasks.
- Returns an explicit, structured HTTP `501 Not Implemented` with stable error identifier `BrowserScrapingDisabled`.
- Preserves 100% of existing authentication behavior (unauthenticated requests continue to fail closed with HTTP 401).
- Preserves all non-browser functionality, including `/api/recrawl`, `/api/health/*`, `/api/status`, `/api/businesses`, `/api/agent/*`, and social scraping's HTTP metadata fallback.
- Added comprehensive regression tests in [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py) and extended [`tests/test_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py).

---

## 2. API Behavior: Before vs. After

| Scenario | Behavior Before Remediation | Behavior After Remediation |
|---|---|---|
| **Authenticated `POST /api/scrape` in Container (Chromium absent)** | Returned HTTP `200 OK` (`{"success": true, "message": "Scraper started..."}`). Child process crashed in background (`Executable doesn't exist`). 0 businesses scraped. | Returns **HTTP `501 Not Implemented`** immediately with structured JSON: `{"detail": {"code": "BrowserScrapingDisabled", "error": "BrowserScrapingDisabled", "message": "..."}}`. **No child process spawned.** |
| **Unauthenticated `POST /api/scrape`** | Returns HTTP `401 Unauthorized` (`"Missing API key"`). | Returns **HTTP `401 Unauthorized`** (`"Missing API key"`). Auth checks strictly take precedence over capability checks. |
| **Authenticated `POST /api/recrawl`** | Dispatches background recrawl task. Runs static analysis without browser. | Dispatches background recrawl task. Runs static analysis without browser. **100% Preserved.** |
| **Liveness & Readiness Probes** | Return HTTP 200. | Return HTTP 200. **100% Preserved.** |
| **Supported Browser Scrape (Chromium present / enabled)** | Dispatches background task; returns HTTP 200. | Dispatches background task; returns HTTP 200. **100% Preserved.** |

---

## 3. Implementation Details

### A. Capability Detection Hierarchy (`api_server.py`)

A new resolution function `is_browser_scraping_available()` was introduced with clear evaluation precedence:

```python
# Browser scraping capability management (Phase 6N-D)
_browser_scraping_checker: Optional[Any] = None


def set_browser_scraping_checker(checker: Optional[Any]) -> None:
    """Override capability checker for tests or custom environments."""
    global _browser_scraping_checker
    _browser_scraping_checker = checker


def is_browser_scraping_available() -> bool:
    """
    Determines whether browser-dependent scraping (Playwright/Chromium) is available.

    Capability Resolution Order:
    1. Check if a programmatic override is set via set_browser_scraping_checker.
    2. Check BROWSER_SCRAPING_ENABLED env var ('true'/'1'/'yes' vs 'false'/'0'/'no').
    3. Check runtime presence and executability of the Chromium binary via Playwright.
    """
    global _browser_scraping_checker
    if _browser_scraping_checker is not None:
        return bool(_browser_scraping_checker())

    override = os.getenv("BROWSER_SCRAPING_ENABLED")
    if override is not None:
        return override.strip().lower() in ("true", "1", "yes", "enabled")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exec_path = p.chromium.executable_path
            return bool(exec_path and os.path.isfile(exec_path) and os.access(exec_path, os.X_OK))
    except Exception as e:
        logger.debug(f"Browser capability check failed: {e}")
        return False
```

### B. Endpoint Guard (`trigger_scrape`)

In [`api_server.py:725-745`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L725-L745):
```python
@app.post("/api/scrape", dependencies=[Depends(verify_api_key)])
async def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Critical fix #1: Lock-protected scrape trigger prevents process collision."""
    source = req.source or "gmaps"

    # Deterministic capability guard (Phase 6N-D):
    # Reject browser-dependent scrapers before acquiring locks or spawning subprocesses
    if source in ("gmaps", "justdial", "indiamart") and not is_browser_scraping_available():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "BrowserScrapingDisabled",
                "error": "BrowserScrapingDisabled",
                "message": (
                    f"Live browser-dependent scraping (source: '{source}') is disabled in this deployment "
                    "because browser binaries (Chromium) are unavailable. "
                    "Pre-load business prospects or deploy a dedicated scraping worker."
                ),
            },
        )

    async with process_lock:
        if is_scraper_running():
            return {"success": False, "message": "Scraper is already running in background."}
        ...
```

---

## 4. How the Guard Distinguishes Browser-Dependent Scraping

1. **Browser-Dependent Connectors:**
   The `ScrapeRequest.source` field permits values matching `^(gmaps|justdial|indiamart)$`:
   - `gmaps` $\rightarrow$ [`GoogleMapsScraper.scrape`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/public_web/google_maps.py) (uses `sync_playwright`)
   - `justdial` $\rightarrow$ [`JustDialScraper.scrape`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/registries/justdial.py) (uses `sync_playwright`)
   - `indiamart` $\rightarrow$ [`IndiaMartScraper.scrape`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/registries/indiamart.py) (uses `sync_playwright`)
   All three are browser-dependent and guarded by `if source in ("gmaps", "justdial", "indiamart") and not is_browser_scraping_available():`.

2. **Non-Browser Operations (Preserved):**
   - **Recrawl:** Invoked via `POST /api/recrawl`. Runs `pipeline_runner.py --recrawl`, which queries overdue PostgreSQL records and runs static website analysis (`requests` + `BeautifulSoup`). Completely bypassed by the guard.
   - **Autonomous Agent:** Invoked via `POST /api/agent/run` and `POST /api/agent/execute`. Uses SQL repository queries and LLM reasoners. Bypassed by the guard.
   - **Deep Social Scraping Fallback:** [`SocialScraper`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/social/social_scraper.py) runs requests Open Graph checks first; if Playwright fails, it catches the error and safely returns the requests result.

---

## 5. Verification & Test Execution Results

### Focused Regression Test Suite: [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py)
Executed: `pytest tests/test_browser_scrape_guard.py -v`
Outcome: **9/9 tests passed in 0.36s**.
- `test_authenticated_scrape_rejected_when_browser_unavailable[gmaps]`: **PASSED**
- `test_authenticated_scrape_rejected_when_browser_unavailable[justdial]`: **PASSED**
- `test_authenticated_scrape_rejected_when_browser_unavailable[indiamart]`: **PASSED**
- `test_subprocess_not_started_when_scrape_rejected`: **PASSED** (asserts no task spawned, process lock unheld, logs untouched)
- `test_unauthenticated_scrape_follows_existing_rules`: **PASSED** (asserts HTTP 401 on missing & invalid keys)
- `test_scrape_accepted_when_browser_available`: **PASSED** (asserts HTTP 200 when capability is active)
- `test_health_and_status_endpoints_unaffected`: **PASSED** (asserts `/api/health/live`, `/api/health/ready`, `/api/status` return 200)
- `test_recrawl_endpoint_unaffected_by_browser_guard`: **PASSED** (asserts `/api/recrawl` returns 200)
- `test_social_scraper_fallback_when_playwright_unavailable`: **PASSED** (asserts Open Graph fallback operates)

### Full Offline Test Suite:
Executed: `pytest -m "not postgres_integration and not docker" -v`
Outcome: **469/469 tests passed in 7.31s** (0 regressions against the 460-test baseline).

### Frontend Unit Test Suite:
Executed: `npm test` in `dashboard/`
Outcome: **45/45 tests passed in 162ms**.

### Container Smoke Tests: [`tests/test_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py)
Added `test_container_rejects_browser_scrape_when_unavailable` to verify in CI container packaging runs that the live container rejects `POST /api/scrape` with 501 and `BrowserScrapingDisabled`.

---

## 6. Limitations & Future Roadmap

- **Limitation:** Live cold harvesting of new Google Maps listings cannot be executed directly from inside the single-replica API container pod. Business prospects must be pre-loaded via database seeding, CSV upload, or recrawl.
- **Future Production Roadmap (Option C):** When transitioning to multi-pod distributed architecture, deploy a dedicated asynchronous worker container (`business-intelligence-scraper`) using `mcr.microsoft.com/playwright/python:v1.42.0-jammy` backed by a task queue.
