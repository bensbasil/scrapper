# Phase 6J.1: Backend API Enablers for the Business Opportunity Intelligence Platform

**Date:** 2026-10-11  
**Status:** Complete  
**Corpus / Repository:** `bensbasil/scrapper`  
**Prerequisite:** Phase 6I-B (Frontend Database Access Boundary Audit)  

---

## 1. Executive Summary

Phase 6I-B identified three backend capability gaps that previously prevented removing direct PostgreSQL queries from the Next.js frontend without regressing application behavior:
1. Absence of `GET /api/businesses/{business_id}/changes` (frontend queried `change_events` directly).
2. Omission of `stage_failure_counts` from `GET /api/runs` (the `/runs` page requires this field for its "Stage Failures / Errors" column).
3. Inability to request opportunity-score ordering on `GET /api/businesses` (frontend SSR required `ORDER BY s.opportunity_score DESC NULLS LAST, b.id DESC`).

In Phase 6J.1, all three gaps were closed entirely within the backend API and database repository layers without modifying the Next.js frontend, without altering database schemas, and without introducing new external dependencies.

---

## 2. Changes Made and Files Affected

| File Path | Component | Changes Implemented |
| :--- | :--- | :--- |
| [`database/db.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/db.py) | `ScraperRepository` | 1. Added `get_change_events(self, business_id: int) -> List[Dict[str, Any]]` querying `change_events` ordered by `detected_at DESC, id DESC`.<br>2. Updated `get_pipeline_runs(self, limit: int = 20)` to include `stage_failure_counts` in the SELECT query and safely deserialize it.<br>3. Updated `get_businesses_for_dashboard(self, limit, offset, sort_by)` to support `sort_by="opportunity"` with `NULLS LAST` and strict SQL allowlist validation. |
| [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py) | FastAPI Server | 1. Added endpoint `GET /api/businesses/{business_id}/changes` with business existence checking (404) and ID validation (400 for `<=0`, 422 for non-int).<br>2. Updated `GET /api/businesses` to accept optional `sort_by` parameter (`"opportunity"`, `"default"`, `"id"`).<br>3. Standardized error sanitization (500 without internal leaks). |
| [`tests/test_api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_api_server.py) | Test Suite | Added mock responses and tests for change events, sort parameters, and `stage_failure_counts` in run summaries. |
| [`tests/test_api_auth.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_api_auth.py) | Test Suite | Added `GET /api/businesses/1/changes` to protected endpoints rejection matrix (401 without auth). |
| [`tests/test_api_error_sanitization.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_api_error_sanitization.py) | Test Suite | Added test verifying database errors on `GET /api/businesses/1/changes` fail closed cleanly as 500 without leaking credentials or queries. |
| [`tests/test_phase6j1_backend_enablers.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_phase6j1_backend_enablers.py) | New Test Suite | Dedicated 11-test suite covering repository unit logic, allowlists, API boundary validation, and real PostgreSQL integration. |

---

## 3. Endpoint and Response Contracts

### 3.1. `GET /api/businesses/{business_id}/changes` (Protected)
- **Authentication:** Required (`X-API-Key` or `Authorization: Bearer <token>`).
- **Path Parameter:** `business_id: int` (must be a positive integer `> 0`).
- **Validation:**
  - Non-integer (e.g. `/changes` with `"abc"`): HTTP 422 Unprocessable Entity.
  - Non-positive integer (`<= 0`): HTTP 400 Bad Request (`{"detail": "Business ID must be a positive integer."}`).
  - Unknown business ID: HTTP 404 Not Found (`{"detail": "Business not found"}`).
  - Unauthenticated: HTTP 401 Unauthorized.
- **Success Response (200 OK):**
```json
{
  "success": true,
  "business_id": 1,
  "changes": [
    {
      "id": 10,
      "business_id": 1,
      "changes": [
        {
          "field": "phone",
          "old": "123-456-7890",
          "new": "987-654-3210"
        }
      ],
      "previous_snapshot_at": "2026-10-10T10:00:00+00:00",
      "current_snapshot_at": "2026-10-11T10:00:00+00:00",
      "change_summary": "Phone number updated",
      "detected_at": "2026-10-11T10:00:00+00:00"
    }
  ]
}
```
- **Empty Response (200 OK):** When a business exists but has no logged changes:
```json
{
  "success": true,
  "business_id": 2,
  "changes": []
}
```

---

### 3.2. `GET /api/runs` (Protected)
- **Authentication:** Required (`verify_api_key`).
- **Query Parameter:** `limit: int = 20`.
- **Response Change:** Each run object in `runs: [...]` now includes `stage_failure_counts: Record<string, number>`.
- **Success Response (200 OK):**
```json
{
  "success": true,
  "runs": [
    {
      "run_id": "run-001",
      "search_query": "dentists in Austin",
      "started_at": "2026-10-11T09:00:00+00:00",
      "finished_at": "2026-10-11T09:05:00+00:00",
      "total_businesses": 15,
      "successful_businesses": 14,
      "failed_businesses": 1,
      "success_rate": 93.3,
      "high_opportunity_count": 4,
      "stage_failure_counts": {
        "scraping": 0,
        "social_audit": 1
      },
      "notes": ["1 timeout on instagram"],
      "created_at": "2026-10-11T09:00:00+00:00"
    }
  ]
}
```

---

### 3.3. `GET /api/businesses` (Protected)
- **Authentication:** Required (`verify_api_key`).
- **Query Parameters:**
  - `limit: Optional[int]` (1 to 1000)
  - `offset: int = 0`
  - `sort_by: Optional[str]` — Accepted values: `"opportunity"`, `"default"`, `"id"`.
- **Validation:**
  - If `sort_by` is provided with an unsupported value: HTTP 400 Bad Request (`{"detail": "Invalid sort_by parameter '...'. Allowed values: 'opportunity', 'default', 'id'."}`).
- **Behavior:**
  - `sort_by` omitted or `"default"` / `"id"`: Orders by `b.id DESC`.
  - `sort_by="opportunity"`: Orders by `s.opportunity_score DESC NULLS LAST, b.id DESC`, precisely matching the frontend SSR query.
- **Success Response (200 OK):**
```json
{
  "success": true,
  "businesses": [...],
  "limit": 10,
  "offset": 0,
  "sort_by": "opportunity"
}
```

---

## 4. SQL and Schema Verification

All queries interact with the existing schema defined in `database/schema.sql` (zero schema migrations required):

1. **`change_events` Table:**
   - Schema: `id SERIAL PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id), changes JSONB, previous_snapshot_at TIMESTAMPTZ, current_snapshot_at TIMESTAMPTZ, change_summary TEXT, detected_at TIMESTAMPTZ`.
   - Index: `idx_change_events_business_id ON change_events(business_id)`.
   - SQL in `get_change_events`:
     ```sql
     SELECT id, business_id, changes, previous_snapshot_at, current_snapshot_at,
            change_summary, detected_at
     FROM change_events
     WHERE business_id = %s
     ORDER BY detected_at DESC, id DESC;
     ```
2. **`pipeline_runs` Table:**
   - Column `stage_failure_counts JSONB DEFAULT '{}'::jsonb` already existed in `schema.sql`.
   - SQL in `get_pipeline_runs`: Added `stage_failure_counts` to the SELECT list.
3. **`businesses` + `scoring_results` Table:**
   - Column `opportunity_score NUMERIC(5, 2)` already existed in `scoring_results`.
   - `ORDER BY s.opportunity_score DESC NULLS LAST, b.id DESC` uses fixed SQL string interpolation from an internal allowlist dictionary, completely neutralizing SQL injection risks.

---

## 5. Security & Validation Behavior

1. **SQL Injection Protection:** Fixed SQL allowlist dictionary for order clauses; all parameters (`business_id`, `limit`, `offset`) use standard PostgreSQL parameterized queries (`%s`).
2. **Authentication Enforcement:** All endpoints enforce `verify_api_key`. When `API_AUTH_TOKEN` is configured, requests without valid credentials return 401 Unauthorized. Incoming token values are never logged.
3. **Information Disclosure Prevention:** Database connection timeouts, syntax errors, or driver errors are caught, logged internally, and sanitized as generic 500 errors (`"An internal error occurred while retrieving change events."`). No passwords, connection strings, or SQL details are returned in HTTP responses.

---

## 6. Verification and Test Results

### 6.1. Unit & Endpoint Tests (`tests/test_phase6j1_backend_enablers.py`)
```bash
/tmp/phase6-env/bin/pytest tests/test_phase6j1_backend_enablers.py -v
```
**Result:** 10 passed in 0.26s.

### 6.2. Existing API Test Suite Updates
```bash
/tmp/phase6-env/bin/pytest tests/test_api_server.py tests/test_api_auth.py tests/test_api_error_sanitization.py -v
```
**Result:** 51 passed, 1 skipped (real postgres test when unconfigured) in 0.35s.

### 6.3. Full Offline Test Suite
```bash
/tmp/phase6-env/bin/pytest -m "not postgres_integration and not docker" -q
```
**Result:** 442 passed, 14 deselected in 8.01s.

### 6.4. Live PostgreSQL Integration Tests
Executed against a live PostgreSQL 15 container (`bi-postgres:15-alpine` on port 5433):
```bash
TEST_DATABASE_URL="postgresql://bi_user:bi_password@127.0.0.1:5433/bi_db" /tmp/phase6-env/bin/pytest tests/test_phase6j1_backend_enablers.py -m "postgres_integration" -v
```
**Result:** 1 passed in 0.29s.
Verified against real PostgreSQL:
- Created and retrieved pipeline runs with `stage_failure_counts` JSONB.
- Inserted businesses and scoring results, verifying `s.opportunity_score DESC NULLS LAST, b.id DESC` ordering.
- Inserted and retrieved `change_events` rows with proper JSON array parsing and ISO timestamp serialization.

### 6.5. Frontend Proxy Tests
Executed inside Node.js 20 container:
```bash
docker run --rm -v "$(pwd)/dashboard":/app -w /app node:20 npm test
```
**Result:** 23 passed, 0 failed in 150ms.

---

## 7. Readiness for Phase 6J.2

All three backend enablers are deployed and verified. Phase 6J.2 can safely proceed with:
1. Creating `dashboard/src/lib/apiClient.ts` to replace direct PostgreSQL queries in server components with authenticated server-to-backend fetch calls.
2. Updating `/` (`page.tsx`) to declare `export const dynamic = 'force-dynamic'` and fetch from `/api/businesses?sort_by=opportunity`.
3. Updating `/business/[id]/page.tsx` to fetch detail from `/api/businesses/{id}`, change events from `/api/businesses/{id}/changes`, and outreach drafts from `/api/businesses/{id}/outreach`.
4. Updating `/runs/page.tsx` to fetch run history from `/api/runs`.
5. Removing `dashboard/src/lib/db.ts` and uninstalling `pg` and `@types/pg`.
