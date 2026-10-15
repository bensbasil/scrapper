# Phase 6N-D.3: Read-Only Review of Browser Scraping Capability Guard

**Project:** Business Opportunity Intelligence Platform  
**Repository:** `scrapper`  
**Date:** 2026-10-15  
**Review Type:** Read-Only Forensic Audit & Defect Analysis (Phase 6N-D.3)  
**Baseline Commit:** `0c61d28` (*fix(ci): separate frontend unit and container smoke tests*)  
**Reviewed Commit:** `4540826` (*Phase 6N-D.2 Remediation: Deterministic Browser Capability Guard*)  
**Status:** Completed  

---

## 1. Executive Summary

This audit performs an independent, read-only architectural and behavioral review of the Browser Scraping Capability Guard implemented during Phase 6N-D.2 in response to audit finding P0-1.

The investigation evaluated the changes across:
- [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py) (lines 157–195, 725–775)
- [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py)
- [`tests/test_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py) (lines 194–219)
- [`AI_MEMORY/PHASE_6N_D_BROWSER_SCRAPING_REMEDIATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6N_D_BROWSER_SCRAPING_REMEDIATION.md)
- Docker & Kubernetes configurations ([`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile), [`deploy/docker-compose.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/docker-compose.yaml), [`deploy/kubernetes/`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes))

### Summary Scorecard

| # | Investigation Question | Finding Verdict | Defect vs. Concern |
|---|---|---|---|
| **Q1** | Can `BROWSER_SCRAPING_ENABLED=true` cause API to accept browser scraping when Chromium is missing/unusable? | **YES** | **Confirmed Defect / Config Hazard** |
| **Q2** | Does capability check verify launch viability, or only executable path? | **Executable path only** | **Design Characteristic / Theoretical Risk** |
| **Q3** | Does default behavior reliably reject browser scraping in current container? | **YES** | **Verified Functional** |
| **Q4** | Is check performed at correct point (after auth, before background work)? | **YES** | **Verified Correct** |
| **Q5** | Could check or test hook introduce concurrency or configuration problems? | **YES** (Blocking event loop, no caching, global mutable hook) | **Confirmed Defect (Event Loop Blocking) & Theoretical Risks** |
| **Q6** | Are tests sufficient to verify default container behavior (not merely mocked)? | **NO** (Unit tests 100% mocked; un-mocked only in Docker smoke test) | **Confirmed Test Suite Gap** |

---

## 2. Detailed Findings by Investigation Question

### Question 1: Can `BROWSER_SCRAPING_ENABLED=true` cause the API to accept browser-dependent scraping when Chromium is missing or unusable?

**Finding: YES.** (Confirmed Defect / Configuration Hazard)

#### Evidence:
In [`api_server.py:183-185`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L183-L185):
```python
override = os.getenv("BROWSER_SCRAPING_ENABLED")
if override is not None:
    return override.strip().lower() in ("true", "1", "yes", "enabled")
```
When `BROWSER_SCRAPING_ENABLED` is set to any truthy value (`true`, `1`, `yes`, `enabled`):
1. `is_browser_scraping_available()` immediately returns `True` at line 185.
2. It completely bypasses lines 187–195 (the Playwright executable existence check).
3. In [`api_server.py:732`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L732), `if source in ("gmaps", "justdial", "indiamart") and not is_browser_scraping_available():` evaluates to `False`.
4. The guard does not raise HTTP 501. The endpoint returns HTTP 200 OK (`{"success": true, "message": "Scraper started successfully in background."}`).
5. In the background task, `pipeline_runner.py` spawns and executes `google_maps.py` (or `justdial.py`/`indiamart.py`), calling `p.chromium.launch()`.
6. `p.chromium.launch()` raises `playwright._impl._errors.Error: Executable doesn't exist...`, crashing the scraper run.

#### Empirical Verification:
We executed an isolated test in Python:
```bash
$ BROWSER_SCRAPING_ENABLED=true PLAYWRIGHT_BROWSERS_PATH=/tmp/empty python -c "
import api_server
print(api_server.is_browser_scraping_available())
"
# Output: True
```
Even with an empty browser directory, `is_browser_scraping_available()` returns `True`.

#### Smallest Safe Correction:
Treat `BROWSER_SCRAPING_ENABLED` strictly as an administrative kill-switch when disabled, but require physical binary validation when enabled or unset:
```python
override = os.getenv("BROWSER_SCRAPING_ENABLED")
if override is not None and override.strip().lower() in ("false", "0", "no", "disabled"):
    return False

# When BROWSER_SCRAPING_ENABLED is true or unset, probe physical binary existence
```

#### Regression Test Needed:
```python
def test_browser_scraping_enabled_true_does_not_bypass_missing_binary(monkeypatch):
    monkeypatch.setenv("BROWSER_SCRAPING_ENABLED", "true")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/tmp/nonexistent_browsers_dir")
    set_browser_scraping_checker(None)
    assert is_browser_scraping_available() is False
```

---

### Question 2: Does the capability check verify actual browser launch viability, or only the executable path?

**Finding: Only verifies executable path and file execute permissions (`os.path.isfile(exec_path) and os.access(exec_path, os.X_OK)`). It does NOT verify browser launch viability.** (Design Characteristic / Theoretical Risk)

#### Evidence:
In [`api_server.py:187-195`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L187-L195):
```python
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exec_path = p.chromium.executable_path
        return bool(exec_path and os.path.isfile(exec_path) and os.access(exec_path, os.X_OK))
except Exception as e:
    logger.debug(f"Browser capability check failed: {e}")
    return False
```
`p.chromium.executable_path` queries Playwright's metadata dictionary for the expected executable path of Chromium on the host architecture. It does not spawn Chromium.

#### Impact & Theoretical Concern:
- **What it catches:** Missing browser binary file (the exact condition in the current Docker container, where `/home/appuser/.cache/ms-playwright` does not exist).
- **What it misses:**
  1. Missing shared libraries: In minimal Linux base images (`python:3.11-slim`), Chromium requires OS libraries like `libnss3.so`, `libatk-1.0.so.0`, `libasound.so.2`. If the binary file exists but libraries are missing, `os.access(exec_path, os.X_OK)` returns `True`, but actual execution fails at dynamic linking (`ld.so`).
  2. Linux sandbox restrictions: Running Chromium as non-root user `appuser` without `--no-sandbox` or proper kernel seccomp flags can fail at launch.
  3. Corrupted or partially downloaded browser binaries.
- **Architectural Rationale:** Full `launch()` invocation on every check would incur ~200–500ms latency and allocate ~150MB RAM per check. Thus, path inspection is a pragmatic trade-off, but it must be understood as an existence check, not a launch viability check.

---

### Question 3: Does the default behavior reliably reject browser-dependent scraping in the current backend container?

**Finding: YES.** (Verified Functional)

#### Evidence:
1. In the backend Docker image ([`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile)):
   - Base image is `python:3.11-slim`.
   - `requirements.lock` installs `playwright==1.42.0`.
   - `playwright install chromium` is never run during `docker build`.
   - No `PLAYWRIGHT_BROWSERS_PATH` or `BROWSER_SCRAPING_ENABLED` is set in `Dockerfile`, [`deploy/docker-compose.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/docker-compose.yaml), or [`deploy/kubernetes/base/configmap.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/base/configmap.yaml).
2. Runtime resolution:
   - `_browser_scraping_checker` is `None`.
   - `BROWSER_SCRAPING_ENABLED` is `None`.
   - `exec_path` evaluates to `/home/appuser/.cache/ms-playwright/chromium-<rev>/chrome-linux/chrome`.
   - `/home/appuser/.cache/ms-playwright` does not exist on the filesystem.
   - `os.path.isfile(exec_path)` returns `False`.
   - `is_browser_scraping_available()` returns `False`.
3. In [`api_server.py:732-744`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L732-L744):
   - Scrape requests defaulting to `source="gmaps"` (or explicitly `"justdial"`, `"indiamart"`) trigger the guard.
   - Returns HTTP 501 `Not Implemented` with code `BrowserScrapingDisabled`.
4. Verified in live container test [`tests/test_container_smoke.py:194-219`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py#L194-L219) (`test_container_rejects_browser_scrape_when_unavailable`).

---

### Question 4: Is the browser capability check performed at the correct point in the request flow, after authentication but before any background work?

**Finding: YES.** (Verified Correct Request Flow)

#### Evidence:
1. **Authentication executes first:**
   Line 725: `@app.post("/api/scrape", dependencies=[Depends(verify_api_key)])`
   FastAPI resolves dependencies before invoking the route handler. Unauthenticated requests (missing or invalid `X-API-Key`) abort with HTTP 401 before `trigger_scrape` executes.
2. **Capability check executes before state mutations:**
   In [`api_server.py:728-771`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L728-L771):
   - Line 728: resolves `source = req.source or "gmaps"`
   - Lines 732–744: evaluates `if source in ("gmaps", "justdial", "indiamart") and not is_browser_scraping_available(): raise HTTPException(...)`
   - Line 746: `async with process_lock:`
   - Line 770: `log_history.clear()`
   - Line 771: `background_tasks.add_task(run_scraper_process, args)`
3. **Guaranteed Side-Effect Free Rejection:**
   On HTTP 501 rejection:
   - `process_lock` is never acquired.
   - `log_history` is never cleared.
   - `background_tasks` is never queued.
   - No subprocess (`run_scraper_process`) is spawned.
   - Tested and verified by [`test_subprocess_not_started_when_scrape_rejected`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py#L81-L108).

---

### Question 5: Could the check or its test hook introduce concurrency or configuration problems?

**Finding: YES.** (Confirmed Performance Defect & Concurrency/Configuration Risks)

#### 1. Event Loop Blocking (Confirmed Defect):
- `trigger_scrape` in `api_server.py:726` is an `async def` route handled directly by FastAPI on the asyncio main thread.
- Inside `is_browser_scraping_available()`, `with sync_playwright() as p:` starts a synchronous Node/Playwright driver subprocess via pipes and IPC.
- Empirical benchmark: `with sync_playwright() as p:` takes **90ms to 185ms** on each invocation.
- Because it is synchronous and un-awaited, it **blocks the entire asyncio event loop** for up to 185ms whenever a scrape request is evaluated. Concurrent requests to `/api/health/live`, `/api/health/ready`, or dashboard API proxies will experience latency spikes.

#### 2. Lack of Result Caching (Confirmed Inefficiency):
- `is_browser_scraping_available()` has no memoization or caching.
- In a container, the presence of the browser binary is immutable for the lifetime of the process.
- 10 repeated calls take ~901ms (~90ms per call).

#### 3. Test Hook Concurrency Hazard (`_browser_scraping_checker`):
- `_browser_scraping_checker` is a module-level global variable.
- In multi-threaded Uvicorn workers or parallel test runners (e.g. `pytest -n auto`), writing to a global variable without locks creates data races across concurrent requests.
- It bypasses FastAPI's idiomatic dependency injection system (`app.dependency_overrides`).

#### Smallest Safe Correction:
Memoize the capability check or initialize it once at server startup:
```python
_cached_browser_available: Optional[bool] = None

def is_browser_scraping_available() -> bool:
    global _cached_browser_available, _browser_scraping_checker
    if _browser_scraping_checker is not None:
        return bool(_browser_scraping_checker())

    if _cached_browser_available is not None:
        return _cached_browser_available

    override = os.getenv("BROWSER_SCRAPING_ENABLED")
    if override is not None and override.strip().lower() in ("false", "0", "no", "disabled"):
        _cached_browser_available = False
        return False

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exec_path = p.chromium.executable_path
            _cached_browser_available = bool(exec_path and os.path.isfile(exec_path) and os.access(exec_path, os.X_OK))
    except Exception as e:
        logger.debug(f"Browser capability check failed: {e}")
        _cached_browser_available = False

    return _cached_browser_available
```

---

### Question 6: Are the tests sufficient to verify the default container behavior, not merely mocked capability results?

**Finding: NO.** (Confirmed Test Suite Gap)

#### Evidence:
1. **100% Mocked in Unit Test Suite:**
   In [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py):
   - Lines 58, 86, 115, 142, 170, 198 all set `set_browser_scraping_checker(lambda: False)` or `(lambda: True)`.
   - **Zero unit tests** invoke `is_browser_scraping_available()` in its default un-mocked state.
   - Lines 183–195 of `api_server.py` have 0% coverage within `test_browser_scrape_guard.py`.
2. **Container Smoke Test is Docker-Gated:**
   - [`tests/test_container_smoke.py:194`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py#L194) (`test_container_rejects_browser_scrape_when_unavailable`) is the ONLY test verifying un-mocked behavior.
   - However, `test_container_smoke.py` is skipped unless Docker is installed and running (`@pytest.mark.skipif(not is_docker_available())`).
   - In CI job `test-offline` (`pytest -m "not postgres_integration and not docker"`), the Docker smoke tests do not run.
   - Therefore, default un-mocked capability detection is completely untested in offline CI and developer environments without Docker.
3. **Missing Environment Variable Tests:**
   Neither `test_browser_scrape_guard.py` nor `test_container_smoke.py` tests `BROWSER_SCRAPING_ENABLED=true` or `BROWSER_SCRAPING_ENABLED=false`.

#### Regression Tests Needed:
Add un-mocked unit tests in `tests/test_browser_scrape_guard.py`:
```python
def test_default_detection_with_missing_browser_path(monkeypatch):
    """Verify un-mocked capability detection returns False when browser directory is empty."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/tmp/empty_test_browsers_dir")
    monkeypatch.delenv("BROWSER_SCRAPING_ENABLED", raising=False)
    set_browser_scraping_checker(None)
    assert is_browser_scraping_available() is False

def test_browser_scraping_enabled_false_env_override(monkeypatch):
    """Verify BROWSER_SCRAPING_ENABLED=false reliably disables scraping."""
    monkeypatch.setenv("BROWSER_SCRAPING_ENABLED", "false")
    set_browser_scraping_checker(None)
    assert is_browser_scraping_available() is False
```

---

## 3. Configuration & Deployment Audit

Audit of browser-related configuration across deployment manifests:

1. **`Dockerfile`:**
   - Correctly omits `playwright install` to maintain a lightweight (~250MB), non-root container image.
   - Does NOT set `PLAYWRIGHT_BROWSERS_PATH` or `BROWSER_SCRAPING_ENABLED`.
2. **`deploy/docker-compose.yaml`:**
   - Service `backend`: no browser-related variables defined. Operates under default safe guard behavior.
3. **`deploy/kubernetes/base/configmap.yaml` & `deployment.yaml`:**
   - No browser-related variables defined. Operates under default safe guard behavior.
4. **`deploy/kubernetes/overlays/prod/`:**
   - No browser-related variables defined. Operates under default safe guard behavior.

---

## 4. Tests Inspected

1. [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py) (9 tests, all passing):
   - `test_authenticated_scrape_rejected_when_browser_unavailable[gmaps|justdial|indiamart]`
   - `test_subprocess_not_started_when_scrape_rejected`
   - `test_unauthenticated_scrape_follows_existing_rules`
   - `test_scrape_accepted_when_browser_available`
   - `test_health_and_status_endpoints_unaffected`
   - `test_recrawl_endpoint_unaffected_by_browser_guard`
   - `test_social_scraper_fallback_when_playwright_unavailable`
2. [`tests/test_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py) (Lines 194–219):
   - `test_container_rejects_browser_scrape_when_unavailable`
3. [`tests/test_kubernetes_manifests.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_kubernetes_manifests.py):
   - Verified that K8s manifests adhere to non-root execution and security contexts.

---

## 5. Final Assessment: Are Current Changes Safe to Commit?

### Verdict: **CONDITIONALLY SAFE (Safe for Default Container, but Requires P1 Hardening Patch)**

1. **Why it is safe for the immediate baseline:**
   Under default container execution (where `BROWSER_SCRAPING_ENABLED` is unset), the guard works as intended. Authenticated scrape requests return HTTP 501 `BrowserScrapingDisabled`, background processes are not spawned, locks are unheld, auth rules are enforced, and non-browser endpoints (`recrawl`, `health`, `agent`) are unaffected.

2. **Required Follow-up Hardening (Smallest Safe Patch):**
   Before deploying to environments where operators might configure environment variables, apply the following 3 surgical improvements:
   - **Fix Q1 defect:** Prevent `BROWSER_SCRAPING_ENABLED=true` from bypassing physical binary validation.
   - **Fix Q5 defect:** Memoize/cache `is_browser_scraping_available()` so that `sync_playwright()` does not block the asyncio event loop on repeated scrape requests.
   - **Fix Q6 gap:** Add offline unit tests in `tests/test_browser_scrape_guard.py` for un-mocked browser detection and environment variable parsing.
