# Phase 6N-D.4: Browser Scraping Capability Guard Hardening Report

**Project:** Business Opportunity Intelligence Platform  
**Repository:** `scrapper`  
**Date:** 2026-10-15  
**Review Reference:** [`AI_MEMORY/PHASE_6N_D_BROWSER_GUARD_REVIEW.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6N_D_BROWSER_GUARD_REVIEW.md)  
**Remediation Reference:** [`AI_MEMORY/PHASE_6N_D_BROWSER_SCRAPING_REMEDIATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6N_D_BROWSER_SCRAPING_REMEDIATION.md)  
**Status:** Completed & Validated  

---

## 1. Executive Summary

During the Phase 6N-D.3 Read-Only Audit, two key defects/hazards were confirmed in the initial Phase 6N-D.2 browser capability guard:
1. **Configuration Bypass Defect:** Setting `BROWSER_SCRAPING_ENABLED=true` unconditionally returned `True`, bypassing physical executable detection and allowing `POST /api/scrape` to accept requests that subsequently crashed in the background when Chromium was missing.
2. **Event-Loop Blocking & Repeated Overhead:** The capability check invoked `with sync_playwright() as p:` synchronously on the main asyncio thread for every scrape request (~90–185ms blocking latency) without in-memory caching.
3. **Test Suite Coverage Gap:** 100% of offline unit tests relied on `set_browser_scraping_checker` mocks, leaving the actual Playwright detection and environment-variable resolution paths unverified in offline CI.

In Phase 6N-D.4, we implemented surgical hardening in [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py) and added comprehensive regression tests in [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py).

---

## 2. Defects Identified & Corrected

### Defect 1: Unconditional Truthy Bypass on `BROWSER_SCRAPING_ENABLED`
- **Previous Behavior:**
  ```python
  override = os.getenv("BROWSER_SCRAPING_ENABLED")
  if override is not None:
      return override.strip().lower() in ("true", "1", "yes", "enabled")
  ```
  Setting `BROWSER_SCRAPING_ENABLED=true` returned `True` immediately, even if the Chromium binary was missing or corrupted.
- **Hardened Correction:**
  ```python
  override = os.getenv("BROWSER_SCRAPING_ENABLED")
  if override is not None:
      normalized = override.strip().lower()
      if normalized in ("false", "0", "no", "off", "disabled"):
          return False
  # If BROWSER_SCRAPING_ENABLED is true, 1, or unset, continue to verify actual binary presence!
  ```
  Truthy values no longer force availability. Availability strictly requires a physically present, executable Chromium binary.

### Defect 2: Synchronous Event-Loop Blocking & Missing Memoization
- **Previous Behavior:**
  Every call to `is_browser_scraping_available()` spawned a synchronous Node/Playwright driver subprocess (`with sync_playwright() as p:`) on FastAPI's main asyncio event loop, blocking concurrent request processing for 90–185ms per check.
- **Hardened Correction:**
  Introduced process-lifetime in-memory memoization via `_browser_executable_available: Optional[bool] = None`.
  - On the first call, `_check_chromium_executable_available()` evaluates physical binary presence and execute permissions.
  - The result is cached for the process lifetime because container filesystems are immutable.
  - Subsequent requests resolve in O(1) time without filesystem I/O or subprocess spawning.
  - Provided `reset_browser_scraping_cache()` and `clear_browser_capability_cache()` to enable clean cache resets in test suites and dynamic reconfigurations.
  - Administrative disable overrides (`BROWSER_SCRAPING_ENABLED=false`) are evaluated *before* the cache, preventing environment variable changes from being masked by stale cached values.

### Defect 3: Offline Test Suite Mock Gap
- **Previous Behavior:**
  Unit tests solely exercised `set_browser_scraping_checker(lambda: False)`. The actual fallback logic was only tested in `test_container_smoke.py`, which is skipped when Docker is absent.
- **Hardened Correction:**
  Added 20 new tests in [`tests/test_browser_scrape_guard.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_browser_scrape_guard.py) exercising:
  - Real un-mocked fallback with empty `PLAYWRIGHT_BROWSERS_PATH`.
  - Valid executable files with execute permission (`0o755`).
  - Missing and non-executable files (`0o644`).
  - Resistance to `BROWSER_SCRAPING_ENABLED=true` overrides.
  - Administrative disable values (`false`, `0`, `no`, `off`, `disabled`).
  - Fail-closed behavior on driver crashes and import errors.
  - Cache hits, cache misses, and cache resets.
  - Dynamic environment toggle without cache contamination.
  - End-to-end endpoint rejection via `POST /api/scrape` with un-mocked capability detection.

---

## 3. Environment-Variable Semantics

| Environment Variable | Configured Value | Resolved Capability | Notes |
|---|---|---|---|
| `BROWSER_SCRAPING_ENABLED` | *unset* | Physical check (`True` if Chromium exists & executable, else `False`) | Default container mode. Evaluates to `False` in current backend container. |
| `BROWSER_SCRAPING_ENABLED` | `"false"`, `"0"`, `"no"`, `"off"`, `"disabled"` (case-insensitive, whitespace-trimmed) | **`False`** (forced disabled) | Administrative kill-switch. Bypasses filesystem checks entirely. |
| `BROWSER_SCRAPING_ENABLED` | `"true"`, `"1"`, `"yes"`, `"enabled"` | Physical check (`True` if Chromium exists & executable, else `False`) | **Never forces `True`.** Requires physical Chromium binary to be present. |
| `BROWSER_SCRAPING_ENABLED` | *unrecognized string* (e.g. `"auto"`) | Physical check (`True` if Chromium exists & executable, else `False`) | Defaults to physical capability verification. |

---

## 4. Capability Resolution Hierarchy

```mermaid
flowchart TD
    Start([is_browser_scraping_available]) --> CheckHook{_browser_scraping_checker is set?}
    CheckHook -- Yes --> ReturnHook[Return bool(checker())]
    CheckHook -- No --> CheckEnv{BROWSER_SCRAPING_ENABLED set?}
    
    CheckEnv -- Disabled (false/0/no/off/disabled) --> ReturnFalse[Return False]
    CheckEnv -- Not Disabled / Unset --> CheckCache{_browser_executable_available cached?}
    
    CheckCache -- Cache Hit --> ReturnCached[Return cached boolean]
    CheckCache -- Cache Miss --> ProbePW[Launch Playwright driver and inspect exec_path]
    
    ProbePW -- File exists & X_OK --> CacheTrue[Cache True & Return True]
    ProbePW -- File missing or not X_OK --> CacheFalse[Cache False & Return False]
    ProbePW -- Error / Exception --> LogFail[Log debug, Cache False & Return False]
```

---

## 5. Verification & Test Results

### 1. Focused Guard Test Suite
**Command:** `pytest tests/test_browser_scrape_guard.py -v`  
**Result:** **29/29 PASSED in 0.45s** (9 baseline tests + 20 hardening tests).

- `test_authenticated_scrape_rejected_when_browser_unavailable[gmaps]`: **PASSED**
- `test_authenticated_scrape_rejected_when_browser_unavailable[justdial]`: **PASSED**
- `test_authenticated_scrape_rejected_when_browser_unavailable[indiamart]`: **PASSED**
- `test_subprocess_not_started_when_scrape_rejected`: **PASSED**
- `test_unauthenticated_scrape_follows_existing_rules`: **PASSED**
- `test_scrape_accepted_when_browser_available`: **PASSED**
- `test_health_and_status_endpoints_unaffected`: **PASSED**
- `test_recrawl_endpoint_unaffected_by_browser_guard`: **PASSED**
- `test_social_scraper_fallback_when_playwright_unavailable`: **PASSED**
- `test_capability_missing_chromium_returns_false_unmocked`: **PASSED**
- `test_capability_existing_executable_returns_true`: **PASSED**
- `test_capability_missing_or_inaccessible_executable_returns_false`: **PASSED**
- `test_browser_scraping_enabled_true_cannot_bypass_missing_chromium` (6 variations): **PASSED**
- `test_explicit_disable_values_return_false_even_with_valid_executable` (7 variations): **PASSED**
- `test_unexpected_initialization_or_path_errors_fail_closed`: **PASSED**
- `test_cached_behavior_and_cache_reset`: **PASSED**
- `test_environment_disable_not_cached_improperly`: **PASSED**
- `test_endpoint_scrape_rejected_with_unmocked_missing_browser`: **PASSED**

### 2. Full Offline Python Suite
**Command:** `pytest -m "not postgres_integration and not docker" -v`  
**Result:** **489/489 PASSED, 15 deselected in 9.60s** (0 regressions).

### 3. Frontend Unit Suite
**Command:** `npm test` (in `dashboard/`)  
**Result:** **45/45 PASSED in 152ms** (0 regressions).

### 4. Docker Deployment Smoke Tests
**Command:** `pytest tests/test_container_smoke.py -v`  
**Result:** **9 SKIPPED** (`Docker daemon is not available on this host. Deployment smoke tests require Docker.`).

### 5. Git Diff Cleanliness
**Command:** `git diff --check`  
**Result:** Clean (no whitespace errors or conflict markers).

---

## 6. Remaining Limitations & Architectural Scope

1. **In-Container Browser Limitation:** The backend API container image (`python:3.11-slim`) intentionally does not bundle Chromium binaries to maintain container security, minimize attack surface, and keep image size lean (~250MB vs ~1.2GB).
2. **Cold Harvest Live Scraping:** Live scraping of Google Maps/JustDial from inside the single-pod API container remains unsupported by design. Prospects should be pre-loaded, or recrawled via the static HTTP recrawl engine (`POST /api/recrawl`).
3. **Dedicated Scraper Worker Roadmap:** If live browser-dependent harvesting is required in production, deploy a dedicated asynchronous worker pod with task queue dispatching, as recommended in architectural roadmap Option C.
