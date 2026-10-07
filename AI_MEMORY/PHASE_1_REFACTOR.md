# Phase 1 — Interface Refactor Report (P6)

**Date:** 2026-10-07  
**Scope:** Incremental interface decoupling for domain analyzers and persistence isolation for API routes  
**Status:** P6 Complete  

---

## Changes Made

| File | Change | Reason | Risk |
|---|---|---|---|
| [`business_intelligence/competitor_analyzer.py`](file:///Users/ashik/Bens%20Repository/scrapper/business_intelligence/competitor_analyzer.py) | Made `repo` optional in `__init__` (`repo: Optional[Any] = None`) and added `raw_competitors: Optional[List[Dict[str, Any]]] = None` parameter to `analyze()` | Decouples domain intelligence from database access so analyzers can execute as pure domain functions without a database connection, while preserving backward compatibility | Low |
| [`intent/review_trend_detector.py`](file:///Users/ashik/Bens%20Repository/scrapper/intent/review_trend_detector.py) | Preserved pre-supplied `previous_rating` instead of unconditionally overwriting from DB, and added `save_snapshot: bool = True` guard | Decouples intent detection from mandatory database lookup/storage so it can be called as a pure domain function with historical data supplied directly | Low |
| [`database/db.py`](file:///Users/ashik/Bens%20Repository/scrapper/database/db.py) | Added 4 CRUD persistence methods to `ScraperRepository`: `delete_all_businesses()`, `delete_business()`, `batch_delete_businesses()`, and `update_business()` | Enforces the Persistence boundary by centralizing SQL mutation logic inside the repository layer rather than letting API routes execute raw SQL | Low |
| [`api_server.py`](file:///Users/ashik/Bens%20Repository/scrapper/api_server.py) | Replaced direct `with db_manager.get_connection()` SQL executions in `DELETE /api/businesses`, `DELETE /api/businesses/{id}`, `POST /api/businesses/batch-delete`, and `PATCH /api/businesses/{id}` with calls to `repo.*` | Eliminates raw SQL execution from API route handlers, adhering to the Database Boundary defined in P4 | Low |
| [`tests/test_refactored_interfaces.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_refactored_interfaces.py) | Created 12 unit tests using standard `unittest` covering decoupled domain analyzers, repository methods, and API route delegation | Validates interface decoupling, backward compatibility, and error handling without external test dependencies | Low |

---

## Interfaces Improved

### 1. `CompetitorAnalyzer` Boundary
- **Before:**
  ```python
  class CompetitorAnalyzer:
      def __init__(self, repo: Any):
          self.repo = repo
      def analyze(self, business_id: int, business_name: str, category: Optional[str], address: Optional[str], opportunity_score: float) -> CompetitorAnalysisResult:
          raw_competitors = self.repo.get_local_competitors(city, category, business_id)
  ```
  *Problem:* Mandatory DB repository injection prevented running the analyzer in-memory or in an isolated agent tool environment without an active PostgreSQL instance.
- **After:**
  ```python
  class CompetitorAnalyzer:
      def __init__(self, repo: Optional[Any] = None):
          self.repo = repo
      def analyze(
          self,
          business_id: int,
          business_name: str,
          category: Optional[str],
          address: Optional[str],
          opportunity_score: float,
          raw_competitors: Optional[List[Dict[str, Any]]] = None,
      ) -> CompetitorAnalysisResult:
          if raw_competitors is None:
              raw_competitors = self.repo.get_local_competitors(...) if self.repo else []
  ```
  *Benefit:* Pure domain capability. Future agents, orchestrators, or unit tests can pass pre-queried competitor entities directly into `analyze()`. When `raw_competitors` is omitted and `repo` is provided, existing pipeline behavior is 100% preserved.

---

### 2. `ReviewTrendDetector` Boundary
- **Before:**
  ```python
  def analyze(self, business_name, current_rating, review_count, business_id=None, previous_rating=None, review_texts=None):
      if business_id is not None and self.repo is not None:
          prev_snapshot = self.repo.get_latest_review_snapshot(business_id)
          if prev_snapshot:
              previous_rating = float(prev_snapshot["rating"])  # OVERWROTE passed previous_rating
          self.repo.insert_review_snapshot(...)
  ```
  *Problem:* Pre-supplied `previous_rating` was ignored and overwritten if a DB record existed, forcing DB interaction.
- **After:**
  ```python
  def analyze(
      self,
      business_name,
      current_rating,
      review_count,
      business_id=None,
      previous_rating=None,
      review_texts=None,
      save_snapshot=True,
  ):
      if business_id is not None and self.repo is not None:
          if previous_rating is None:
              prev_snapshot = self.repo.get_latest_review_snapshot(business_id)
              if prev_snapshot:
                  previous_rating = float(prev_snapshot["rating"])
          if save_snapshot:
              self.repo.insert_review_snapshot(...)
  ```
  *Benefit:* Can evaluate review trends in-memory without database access when `previous_rating` is passed and `repo=None`.

---

### 3. API Route Persistence Boundary
- **Before:**
  `api_server.py` executed raw inline SQL (`cur.execute("DELETE FROM businesses WHERE id = %s", ...)` and `cur.execute("UPDATE businesses SET ...")`) directly via `db_manager.get_connection()`.
- **After:**
  All route mutations are strictly delegated to `ScraperRepository` methods:
  - `repo.delete_all_businesses()`
  - `repo.delete_business(numeric_id)`
  - `repo.batch_delete_businesses(int_ids)`
  - `repo.update_business(business_id, updates)`
- **Benefit:** Closes the API raw SQL boundary violation identified in P4. `api_server.py` now contains zero raw SQL statements.

---

## Tests

### Executed Tests

1. **`tests/test_refactored_interfaces.py`** (12 tests)
   - `test_pure_domain_execution_without_db` (`CompetitorAnalyzer`): **PASSED**
   - `test_backward_compatibility_with_mock_repo` (`CompetitorAnalyzer`): **PASSED**
   - `test_pure_domain_execution_without_db` (`ReviewTrendDetector`): **PASSED**
   - `test_backward_compatibility_with_mock_repo` (`ReviewTrendDetector`): **PASSED**
   - `test_delete_all_businesses` (`ScraperRepository`): **PASSED**
   - `test_delete_business` (`ScraperRepository`): **PASSED**
   - `test_batch_delete_businesses` (`ScraperRepository`): **PASSED**
   - `test_update_business` (`ScraperRepository`): **PASSED**
   - `test_delete_all_businesses_delegation` (`api_server`): **PASSED**
   - `test_delete_single_business_delegation` (`api_server`): **PASSED**
   - `test_batch_delete_businesses_delegation` (`api_server`): **PASSED**
   - `test_update_business_field_delegation` (`api_server`): **PASSED**
   - *Result:* **12/12 PASSED (0.21s)**

2. **`tests/test_schemas.py`** (8 tests)
   - Schema instantiation, default validation, Pydantic v2 serialization, and dataclass adapter: **PASSED**
   - *Result:* **8/8 PASSED (0.002s)**

3. **Module Importability Verification**
   - `pipeline_runner.py`: **Clean Import (0 errors)**
   - `api_server.py`: **Clean Import (0 errors)**

### Pre-Existing Test Failures (Reported Accurately)
- Running `python -m unittest discover tests` encounters `ModuleNotFoundError: No module named 'pytest'` for:
  - `tests/test_api_server.py`
  - `tests/test_entity_resolver.py`
  - `tests/test_outreach_generator.py`
  - `tests/test_scoring_engine.py`
  - `tests/test_social_scraper.py`
- *Cause:* These legacy test files import `pytest` and `httpx`, which are not present in `requirements.txt` and were not installed in the virtual environment. As per strict instructions, no unrequested dependencies were installed, and no existing test files were altered.

---

## Deferred Work

The following architectural improvements were evaluated in P4/P5 and intentionally deferred from P6:

1. **Shared HTML/DOM In-Memory Caching:**
   - Passing a pre-fetched `RawScrapeSnapshot` from `WebsiteAnalyzer` to `TechStackDetector`, `EmailExtractor`, `DecisionMakerFinder`, `FreshnessMonitor`, `ConversionAnalyzer`, and `TrustSignalDetector` requires synchronized signature modifications across 7 active modules and `pipeline_runner.py`. Deferred to avoid large-scale pipeline churn.
2. **Next.js Direct PostgreSQL Decoupling:**
   - Retiring `dashboard/src/lib/db.ts` and refactoring Next.js server components to query FastAPI REST endpoints requires active frontend React/Next.js component modifications. Deferred to frontend-focused tasks.
3. **Repository Decomposition:**
   - Splitting `ScraperRepository` (1,312 lines) into `BusinessRepository`, `AuditRepository`, `IntelligenceRepository`, etc. Deferred to avoid wide-scale repository refactoring.
4. **Retirement of Dead Stubs in `analyzer/`:**
   - Removing the 6 placeholder stubs (`business_health_score.py`, `competitor_analyzer.py`, etc.) and orphaned `scraper/pipeline.py` is deferred to cleanup tasks.

---

## Compatibility

- **`pipeline_runner.py`:** 100% backward compatible. All existing call sites instantiate `CompetitorAnalyzer(repo=self.repo)` and `ReviewTrendDetector(repo=self.repo)` and invoke `.analyze()` with existing positional arguments without error.
- **FastAPI Endpoints:** 100% backward compatible. Request schemas (`BatchDeleteRequest`, `UpdateBusinessRequest`), response payloads (`{"success": True, ...}`), status codes, and error formatting remain identical.
- **Database Schema:** 0 schema changes, 0 migrations required.

---

`P6 STATUS: COMPLETE`
