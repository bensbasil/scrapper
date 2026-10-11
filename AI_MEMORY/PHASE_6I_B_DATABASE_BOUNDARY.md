# Phase 6I-B: Frontend Database Access Boundary Audit

**Date:** 2026-10-11  
**Status:** Complete  
**Corpus / Repository:** `bensbasil/scrapper`  
**Prerequisite:** Phase 6I-A (Reproducible Local Multi-Container Deployment)  

---

## 1. Executive Summary & Verdict

Phase 6I-A established a functional three-tier Docker Compose deployment comprising PostgreSQL 15, FastAPI, and Next.js. During integration, an architectural duality was identified:
- Interactive UI operations (prospect updates, scrape triggering, SSE logs, bulk deletions) communicate through the Next.js server-side API proxy to FastAPI (`/api/*`).
- Server-rendered pages (`/`, `/business/[id]`, `/runs`) execute direct SQL queries against PostgreSQL using `pg.Pool` via `dashboard/src/lib/db.ts`.

### Core Question
*Can frontend database access (`pg.Pool`, `DATABASE_URL`, direct SQL) be removed safely right now without changing application behavior using only existing backend endpoints?*

### Verified Verdict: NO (Immediate Removal Would Break Application Behavior)
Direct database access **cannot** be removed immediately using only the currently deployed FastAPI endpoints without regressing functionality. Specifically:
1. **Missing Backend Endpoint (`change_events`):** The business detail page (`/business/[id]`) queries the `change_events` table. FastAPI has no endpoint for change events, and `database/db.py` (`ScraperRepository`) has no read method for this table. Removing direct DB queries now would silently delete change event history from the UI.
2. **Field Discrepancy on Pipeline Runs (`stage_failure_counts`):** The run history page (`/runs`) displays a dedicated "Stage Failures / Errors" column derived from `stage_failure_counts`. The existing `GET /api/runs` endpoint omits `stage_failure_counts` (it only returns summary counts and `notes`). Naive migration would render this column empty.
3. **Report Nesting Shape Discrepancy:** Direct query in `businessDetail.ts` maps fields into a nested `business.report` structure expected by `business/[id]/page.tsx`. `GET /api/businesses/{id}` returns a flat dictionary. Calling the backend without an adapter breaks detail page report rendering.
4. **Ordering Disparity:** The homepage SSR query sorts by `opportunity_score DESC NULLS LAST, b.id DESC`, whereas `GET /api/businesses` sorts strictly by `b.id DESC`.
5. **Static Prerender Anomaly:** `dashboard/src/app/page.tsx` lacks `export const dynamic = 'force-dynamic'`. Next.js prerenders `/` at Docker build time (where `DATABASE_URL` is unset), baking `MOCK_BUSINESSES` into static HTML. Real data is only loaded on the client via `BusinessDashboard.tsx` calling `/api/businesses`.

### Recommended Path Forward
Produce this boundary audit report without forcing a hasty redesign. Schedule a structured, two-step migration for Phase 6J where the backend API is extended with the two missing fields/endpoints, followed by retiring `pg` and `db.ts`.

---

## 2. Complete Inventory of Direct Database Access

Across `dashboard/`, database operations are localized to exactly 5 query sites and 1 connection manager module:

| File Path | Function / Query Site | Direct DB Dependency | SQL Target Tables |
| :--- | :--- | :--- | :--- |
| `dashboard/src/lib/db.ts` | `query(text, params)` | `import { Pool } from 'pg'`, `process.env.DATABASE_URL` | N/A (Connection pool manager) |
| `dashboard/src/lib/businesses.ts` | `getBusinesses()` | `import { query } from "./db"` | `businesses`, `scoring_results`, `email_intelligence`, `tech_stacks`, `intent_profiles`, `decision_makers` |
| `dashboard/src/lib/businessDetail.ts` | `getBusinessDetail(id)` | `import { query } from "./db"` | `businesses`, `scoring_results`, `business_reports`, `email_intelligence`, `tech_stacks`, `business_health_profiles`, `competitor_analysis`, `customer_pain_signals`, `decision_makers` |
| `dashboard/src/app/business/[id]/page.tsx` | `getChangeEvents(businessId)` | `import { query } from "@/lib/db"` | `change_events` |
| `dashboard/src/app/business/[id]/page.tsx` | `getOutreachDrafts(businessId)` | `import { query } from "@/lib/db"` | `outreach_drafts` |
| `dashboard/src/app/runs/page.tsx` | `getPipelineRuns()` | `import { query } from "@/lib/db"` | `pipeline_runs` |

No browser-facing client components import `pg` or `db.ts`. All queries execute strictly on the Node.js server during Next.js rendering.

---

## 3. Affected Pages, Components, and Data-Access Functions

### 3.1. Route: `/` (`dashboard/src/app/page.tsx`)
- **Server Component:** `Home()`
- **Data Access:** Calls `getBusinesses()` in `dashboard/src/lib/businesses.ts`.
- **Rendered Component:** Passes `businesses` as `initialBusinesses` prop to `<BusinessDashboard />` (`dashboard/src/components/BusinessDashboard.tsx`).
- **Interactive Component Behavior:** On client mount, `BusinessDashboard.tsx` invokes `fetchLatest()`, which issues a client `fetch("/api/businesses")` through the Next.js API proxy (`/api/[[...path]]/route.ts`). If successful, the client state replaces `initialBusinesses` with the API response.

### 3.2. Route: `/business/[id]` (`dashboard/src/app/business/[id]/page.tsx`)
- **Server Component:** `BusinessDetail({ params })`
- **Data Access:**
  1. `getBusinessDetail(id)` via `dashboard/src/lib/businessDetail.ts`
  2. `getChangeEvents(id)` local server function
  3. `getOutreachDrafts(id)` local server function
- **Rendered Components:**
  - Business title, opportunity score gauge, website link
  - Health Profile widget (`overall_health_score`, `website_health_score`, etc.)
  - Customer Pain Signals & Complaints list
  - Competitor Gap Analysis table
  - Outreach Angles & Recommendations
  - `<StatusSelect />` (interactive client component using `PATCH /api/businesses/[id]`)
  - Change History timeline (renders `changes` from `change_events`)
  - Outreach draft cards (renders `cold_email_draft`, `whatsapp_draft`, etc.)

### 3.3. Route: `/runs` (`dashboard/src/app/runs/page.tsx`)
- **Server Component:** `RunsHistoryPage()`
- **Data Access:** Calls `getPipelineRuns()` locally.
- **Rendered Components:**
  - Summary metric cards (Total Pipeline Runs, Average Success Rate, High Opp Leads)
  - Pipeline runs table (`run_id`, `started_at`, `search_query`, `success_rate`, `stage_failure_counts`)

---

## 4. Query-by-Query Endpoint Comparison

### Query 1: `getBusinesses()` (`src/lib/businesses.ts`)
- **Direct SQL:**
  ```sql
  SELECT b.id::text, b.business_name, b.category, b.phone, b.address, b.website as website_url,
         s.opportunity_score, s.website_quality_score, s.seo_score, s.automation_need_score,
         s.likely_service_match, s.detected_pain_points, b.source_platforms, b.google_rating,
         b.review_count, b.jd_rating, b.jd_reviews_count, b.jd_verified, b.im_rating,
         b.im_verified, b.im_gst_verified, COALESCE(b.outreach_status, 'new') AS outreach_status,
         e.extracted_emails, t.cms, t.analytics_tools, t.frontend_framework,
         i.intent_score, i.outreach_urgency,
         (SELECT json_agg(dm) FROM (SELECT name, role, confidence FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers
  FROM businesses b
  LEFT JOIN (SELECT DISTINCT ON (business_id) ... FROM scoring_results ORDER BY business_id, scored_at DESC) s ON b.id = s.business_id
  LEFT JOIN (SELECT DISTINCT ON (business_id) ... FROM email_intelligence ORDER BY business_id, extracted_at DESC) e ON b.id = e.business_id
  LEFT JOIN (SELECT DISTINCT ON (business_id) ... FROM tech_stacks ORDER BY business_id, detected_at DESC) t ON b.id = t.business_id
  LEFT JOIN (SELECT DISTINCT ON (business_id) ... FROM intent_profiles ORDER BY business_id, evaluated_at DESC) i ON b.id = i.business_id
  ORDER BY s.opportunity_score DESC NULLS LAST, b.id DESC
  ```
- **Candidate Endpoint:** `GET /api/businesses` in `api_server.py` line 514 calling `active_repo.get_businesses_for_dashboard(limit, offset)`.
- **Field Match:** 100% column parity.
- **Differences:**
  - **Ordering:** Frontend SSR query sorts by `opportunity_score DESC NULLS LAST, b.id DESC`. Backend endpoint sorts by `b.id DESC`.
  - **Pagination:** Backend supports optional `limit` and `offset`. Frontend SSR fetches all rows.
  - **Auth:** Backend requires `X-API-Key` (`verify_api_key`).
- **Verdict:** Equivalent in schema, minor sort order difference.

---

### Query 2: `getBusinessDetail(id)` (`src/lib/businessDetail.ts`)
- **Direct SQL:** Queries `businesses` joined with `scoring_results`, `business_reports`, `email_intelligence`, `tech_stacks`, `business_health_profiles`, `competitor_analysis`, `customer_pain_signals`, and `decision_makers`.
- **Candidate Endpoint:** `GET /api/businesses/{business_id}` in `api_server.py` line 530 calling `active_repo.get_business_detail_for_dashboard(business_id)`.
- **Field Match:** High parity on database columns.
- **Differences:**
  - **Shape:** In `businessDetail.ts`, `transformRow()` parses `overall_opportunity`, `website_quality_summary`, `seo_summary`, etc. into a nested `report: { ... }` object. The page component explicitly relies on `business.report`. In `api_server.py`, `detail` contains these fields flat at the top level.
  - **Error Handling:** On missing business, backend returns HTTP 404 (`{"detail": "Business not found."}`). Frontend SSR returns `null`, triggering Next.js `notFound()`.
- **Verdict:** Equivalent data source, requires client adapter function to preserve `report` nesting.

---

### Query 3: `getChangeEvents(businessId)` (`src/app/business/[id]/page.tsx`)
- **Direct SQL:**
  ```sql
  SELECT id, changes, previous_snapshot_at, current_snapshot_at, change_summary, detected_at
  FROM change_events
  WHERE business_id = $1
  ORDER BY detected_at DESC
  ```
- **Candidate Endpoint:** **NONE EXISTS.**
- **Repository Inspection:** `ScraperRepository` in `database/db.py` contains `log_change_event()` (INSERT), but no method to query `change_events`.
- **Verdict:** **Requires a new backend endpoint.** Migrating without a new endpoint would eliminate the change detection timeline feature.

---

### Query 4: `getOutreachDrafts(businessId)` (`src/app/business/[id]/page.tsx`)
- **Direct SQL:**
  ```sql
  SELECT pain_point_positioning, concise_audit_summary,
         cold_email_draft, whatsapp_draft, ai_prompt_template, generated_at
  FROM outreach_drafts
  WHERE business_id = $1
  ORDER BY generated_at DESC
  LIMIT 1
  ```
- **Candidate Endpoint:** `GET /api/businesses/{business_id}/outreach` in `api_server.py` line 546 calling `active_repo.get_outreach_drafts(business_id)`.
- **Field Match:** 100% field parity (`db.py` also returns `id`).
- **Response Format:** Backend returns `{"success": true, "outreach": {...}}` or `{"success": true, "outreach": null}`.
- **Verdict:** **Can migrate using existing API endpoint.**

---

### Query 5: `getPipelineRuns()` (`src/app/runs/page.tsx`)
- **Direct SQL:**
  ```sql
  SELECT id::text, run_id, search_query, started_at, finished_at,
         total_businesses, successful_businesses, failed_businesses,
         success_rate, high_opportunity_count, stage_failure_counts,
         business_records, notes
  FROM pipeline_runs
  ORDER BY started_at DESC
  ```
- **Candidate Endpoint:** `GET /api/runs` in `api_server.py` line 727 calling `active_repo.get_pipeline_runs(limit=20)`.
- **Field Discrepancy:**
  - `repo.get_pipeline_runs()` selects: `run_id, search_query, started_at, finished_at, total_businesses, successful_businesses, failed_businesses, success_rate, high_opportunity_count, notes, created_at`.
  - **Omitted Fields:** `stage_failure_counts` and `business_records` are NOT selected in `get_pipeline_runs()`. They only exist in `get_pipeline_run_detail(run_id)`.
  - **UI Impact:** Line 115 of `dashboard/src/app/runs/page.tsx` parses `run.stage_failure_counts` to render badge counters for each stage failure. If migrated to `GET /api/runs`, this column renders blank.
  - **Ordering / Pagination:** Backend defaults to `LIMIT 20` ordered by `created_at DESC`. Frontend SSR selects all runs ordered by `started_at DESC`.
- **Verdict:** **Requires backend endpoint update.** Cannot migrate without adding `stage_failure_counts` to `get_pipeline_runs()`.

---

## 5. Classification Matrix

| Query Site | Target Entity | Existing API Endpoint | Classification | Reason / Gap |
| :--- | :--- | :--- | :--- | :--- |
| `src/lib/businesses.ts` | Businesses list | `GET /api/businesses` | **Can migrate using existing endpoint** | Requires server-side fetch adapter and sort order alignment. |
| `src/lib/businessDetail.ts` | Business detail | `GET /api/businesses/{id}` | **Can migrate using existing endpoint** | Requires adapter to transform flat report fields into nested `business.report`. |
| `src/app/business/[id]/page.tsx` | Change events | None | **Requires a new backend endpoint** | No endpoint or repository query method exists for `change_events`. |
| `src/app/business/[id]/page.tsx` | Outreach drafts | `GET /api/businesses/{id}/outreach` | **Can migrate using existing endpoint** | Full schema parity exists. |
| `src/app/runs/page.tsx` | Pipeline runs | `GET /api/runs` | **Requires backend endpoint update** | `GET /api/runs` omits `stage_failure_counts` required by the runs UI table. |

---

## 6. Mock-Data Fallback & Consistency Analysis

### 6.1. Build-Time Static Prerendering of `/`
In `dashboard/src/app/page.tsx`:
```tsx
export default async function Home() {
  const businesses = await getBusinesses();
  return <BusinessDashboard initialBusinesses={businesses} />;
}
```
Because `page.tsx` does not declare `export const dynamic = 'force-dynamic'`, Next.js treats `/` as a static route (`○ /`) during `next build`.
1. During container image build, `DATABASE_URL` is deliberately unset.
2. `getBusinesses()` throws `Error: DATABASE_URL environment variable is not set`.
3. The `catch` block intercepts the error and returns `MOCK_BUSINESSES` (6 hardcoded dummy prospects).
4. Next.js bakes these 6 dummy prospects into the prerendered HTML payload.
5. In production, every first page load serves `MOCK_BUSINESSES` before hydration.
6. Once the client script loads, `fetchLatest()` runs `fetch("/api/businesses")` and swaps the UI with real data.

### 6.2. Failure Masking Risks
- **Silent Database Outage Masking:** If the database becomes unavailable at runtime, `businessDetail.ts` falls back to `MOCK_BUSINESSES[0]` ("Apex Dental Clinic"). A user navigating to `/business/42` sees fake information for Apex Dental instead of an error or 404 page.
- **Client Hydration Discrepancy:** If `fetchLatest()` in `BusinessDashboard.tsx` fails (e.g. backend 502 Bad Gateway), it silently returns (`if (!res.ok) return;`). The user remains on `MOCK_BUSINESSES` indefinitely without any error banner, mistaking fake data for actual pipeline results.
- **Clear All Reset:** In `BusinessDashboard.tsx` line 252, when a user clicks "Clear All", successful deletion resets state to `MOCK_BUSINESSES` rather than an empty list (`[]`).

---

## 7. Recommended Safe Migration Plan (Phase 6J Roadmap)

To eliminate direct database access cleanly without regressions:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Current Architecture                            │
│                                                                        │
│   Next.js SSR  ──────(Direct SQL via pg.Pool)──────> PostgreSQL       │
│   Next.js Client ───(HTTP Proxy)───> FastAPI ──────> PostgreSQL       │
└────────────────────────────────────────────────────────────────────────┘

                                    ▼

┌────────────────────────────────────────────────────────────────────────┐
│                   Target Architecture (Phase 6J)                       │
│                                                                        │
│   Next.js SSR    ───(Internal Server Fetch)──┐                         │
│                                              ▼                         │
│   Next.js Client ───(HTTP Proxy)───────────> FastAPI ────> PostgreSQL  │
└────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Backend Enablers (Python / FastAPI)
1. **Extend `repo.get_pipeline_runs()`:** Add `stage_failure_counts` to the SELECT query in `database/db.py` line 1498.
2. **Add Change Events Endpoint:**
   - Add `repo.get_change_events(business_id: int)` in `database/db.py`.
   - Expose `GET /api/businesses/{business_id}/changes` in `api_server.py`.
3. **Harmonize Sorting:** Add an optional `sort_by=opportunity` query parameter to `GET /api/businesses` in `api_server.py`.

### Step 2: Frontend Server API Client (`dashboard/src/lib/apiClient.ts`)
Create a lightweight, server-side fetch wrapper for Server Components:
- Uses `getBackendBaseUrl()` (`process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"`).
- Injects `X-API-Key: process.env.API_AUTH_TOKEN`.
- Applies normalization adapters (`transformBusinessDetail`, `transformBusinesses`).
- Replaces mock-data fallbacks with structured error boundaries (`notFound()` or standard Next.js error pages).

### Step 3: Deprecate Frontend DB Layer
1. Add `export const dynamic = 'force-dynamic'` to `dashboard/src/app/page.tsx` to stop static baking of mock data.
2. Remove `dashboard/src/lib/db.ts`.
3. Remove `pg` and `@types/pg` from `dashboard/package.json`.
4. Remove `DATABASE_URL` from frontend container definitions in `deploy/docker-compose.yaml` and Kubernetes manifests.

---

## 8. Verification & Test Evidence

### 8.1. Frontend Proxy Tests
Executed inside `node:20` container:
```bash
docker run --rm -v "$(pwd)/dashboard":/app -w /app node:20 npm test
```
**Output:**
```
TAP version 13
# tests 23
# suites 0
# pass 23
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 135.407167
```
All 23 API proxy tests pass, validating proxy authentication, path traversal guards, SSE streaming, and error handling.

### 8.2. Next.js Production Build
Executed inside `node:20` container:
```bash
docker run --rm -v "$(pwd)/dashboard":/app -w /app node:20 npm run build
```
**Output:**
```
▲ Next.js 16.3.0 (Turbopack)
✓ Running next.config.ts took 65ms
✓ Compiled successfully in 1404ms
  Running TypeScript ...
  Finished TypeScript in 1007ms ...
  Collecting page data using 8 workers ...
  Generating static pages using 8 workers (1/4)
Database query failed. Falling back to mock data: Error: DATABASE_URL environment variable is not set. Add it to .env.local (development) or your deployment environment.
✓ Generating static pages using 8 workers (4/4) in 522ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /api/[[...path]]
├ ƒ /business/[id]
└ ƒ /runs
```
The build completes successfully. The build trace confirms the audit finding: `/` is statically prerendered with mock data due to the lack of `DATABASE_URL` at build time.

### 8.3. Python Test Suite
Executed in local environment:
```bash
/tmp/phase6-env/bin/pytest -m "not postgres_integration and not docker" -q
```
**Output:**
```
424 passed, 13 deselected in 8.30s
```

### 8.4. Kubernetes Manifest Tests
Executed in local environment:
```bash
/tmp/phase6-env/bin/pytest tests/test_kubernetes_manifests.py -q
```
**Output:**
```
12 passed in 0.09s
```

---

## 9. Summary & Handoff

| Item | Status | Verified Result |
| :--- | :--- | :--- |
| Frontend DB Inventory | Complete | Exactly 5 query sites identified across 4 files. |
| Backend Endpoint Mapping | Complete | 3 queries have existing equivalents; 2 queries require backend updates/endpoints. |
| Behavioral Risk Analysis | Complete | Uncovered `stage_failure_counts` omission, `report` nesting disparity, and static prerender mock data anomaly. |
| Test Suite Baseline | Verified | 23/23 frontend proxy tests, 424/424 offline Python tests, 12/12 K8s tests passing. |
| Git Working Tree | Clean / Uncommitted | No commits or pushes performed; audit documented in `AI_MEMORY/PHASE_6I_B_DATABASE_BOUNDARY.md`. |
