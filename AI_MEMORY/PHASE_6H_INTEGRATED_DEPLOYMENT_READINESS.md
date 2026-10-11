# Phase 6H — Integrated Deployment Readiness Review

**Date:** 2026-10-11  
**Role:** Senior Platform & Release Engineer  
**Scope:** Forensic end-to-end deployment readiness audit of the integrated application stack: Next.js frontend container (`business-intelligence-frontend`), server-side API proxy, FastAPI backend container (`business-intelligence-api`), and PostgreSQL database service.  
**Status:** **AUDITED & VALIDATED** (End-to-end 3-container local topology verified live; architectural blockers identified and ranked; zero code regressions)

---

## 1. Executive Summary & Readiness Verdict

### Is the system ready for a controlled local integrated deployment?
**YES, WITH CONFIGURATION DISCIPLINE.**
A live multi-container test was executed on a dedicated user-defined Docker bridge network (`test-bi-net`) with all three services running concurrently:
1. `postgres:15-alpine` (with `database/schema.sql` initialized)
2. `business-intelligence-api:ci` (FastAPI backend on port 8000)
3. `business-intelligence-frontend:test` (Next.js standalone frontend on port 3000)

**Verified End-to-End Result:**
- Next.js root endpoint (`/`) returned HTTP `200 OK` with rendered HTML.
- Public proxy route (`/api/status`) forwarded through the Next.js server proxy to the backend container over internal Docker DNS and returned `{"success":true,"is_running":false,"running_process":false}`.
- Protected proxy route (`/api/businesses`) forwarded through the proxy, injected server-side `X-API-Key`, passed backend `verify_api_key()`, queried PostgreSQL, and returned `{"success":true,"businesses":[],"limit":null,"offset":0}` with zero secret disclosure.
- Backend health readiness (`/api/health/ready`) returned `{"status":"ready","mode":"connected"}` confirming the database connection pool is active.

### What remains before remote production deployment?
1. **Database Schema Initialization Automation:** Clean PostgreSQL instances must have `database/schema.sql` applied before starting application traffic (an empty database causes 500 errors on `/api/businesses` because DDL execution was decoupled from application startup).
2. **Dual Database Access Alignment:** Server-side rendered pages (`page.tsx`, `runs/page.tsx`, `business/[id]/page.tsx`) query PostgreSQL directly using `pg.Pool` if `DATABASE_URL` is set, but fall back to mock data if omitted. For full SSR fidelity, `DATABASE_URL` must be passed to both backend and frontend containers, or SSR routes must be refactored to consume the internal API.
3. **Frontend Kubernetes Packaging (Phase 6I):** Kubernetes manifests currently exist only for the backend API (`deploy/kubernetes/`). Deployment, Service, and Ingress manifests for the frontend pod are required for Kubernetes rollouts.
4. **Remote CI Validation:** While local validation is 100% green, Phase 6G changes are currently uncommitted in the local working tree and have not yet run against remote GitHub Actions.

---

## 2. Complete Deployment Path & Data Architecture

```
                                    BROWSER CLIENT
                                          |
                +-------------------------+-------------------------+
                | (Browser HTTP Traffic)                            | (Static Assets)
                v                                                   v
   +--------------------------+                         +--------------------------+
   | Next.js App Router (SSR) |                         | Next.js Static Chunks    |
   |   src/app/page.tsx       |                         |   public/ & .next/static |
   +------------+-------------+                         +--------------------------+
                |
                +----------------------------+
                |                            |
       (Initial Page SSR)          (Interactive Client APIs)
                |                            |
                |                  fetch("/api/businesses")
                |                  fetch("/api/scrape", POST)
                |                  new EventSource("/api/logs")
                |                            |
                v                            v
   +--------------------------+   +------------------------------------+
   | Direct Database Query    |   | Server-Side API Proxy              |
   |   src/lib/db.ts (pg)     |   |   src/app/api/[[...path]]/route.ts |
   |   src/lib/businesses.ts  |   |   src/lib/apiProxy.ts              |
   +------------+-------------+   +------------------+-----------------+
                |                                    |
                |                     1. Injects server X-API-Key: API_AUTH_TOKEN
                |                     2. Resolves API_INTERNAL_URL via Docker DNS
                |                     3. Strips hop-by-hop & compression headers
                |                     4. Streams SSE & response payloads
                |                                    |
                |                                    v
                |                 +------------------------------------+
                |                 | FastAPI Backend Container          |
                |                 |   business-intelligence-api:ci     |
                |                 |   api_server.py                    |
                |                 |   verify_api_key() (constant time) |
                |                 +------------------+-----------------+
                |                                    |
                |                            ScraperRepository
                |                            DatabaseManager
                |                                    |
                v                                    v
   +-------------------------------------------------------------------+
   | PostgreSQL Database (postgres:15-alpine / Cloud SQL / RDS)        |
   |   schema.sql tables: businesses, scoring_results, pipeline_runs   |
   +-------------------------------------------------------------------+
```

### Analysis of the Dual Data Access Pattern
The application currently exhibits two distinct data retrieval paths:
1. **Interactive Client Operations (Strict API Proxy):**
   All mutations (`POST /api/scrape`, `POST /api/stop`, `DELETE /api/businesses`), background job polling (`GET /api/status`), real-time logs (`GET /api/logs`), and client refreshes (`GET /api/businesses`) flow exclusively through the server-side API proxy to FastAPI. The browser never connects to PostgreSQL and never possesses credentials.
2. **Server-Side Rendered Pages (Direct PostgreSQL Fallback):**
   React Server Components (`page.tsx`, `runs/page.tsx`, `business/[id]/page.tsx`) execute inside the Node.js frontend server process and attempt direct SQL execution via `pg.Pool`.
   - *If `DATABASE_URL` is configured in the frontend container:* Direct queries execute successfully, populating SSR HTML before sending it to the client.
   - *If `DATABASE_URL` is omitted:* `getBusinesses()` catches the error and returns `MOCK_BUSINESSES`. The browser receives the initial mock HTML, then hydration executes `fetchLatest()` (`/api/businesses`), which queries FastAPI and swaps in real data.

---

## 3. Configuration, Authentication & Secret Containment

| Security Control | Implementation | Verification Result |
| :--- | :--- | :--- |
| **Client Bundle Isolation** | `API_AUTH_TOKEN` has no `NEXT_PUBLIC_` prefix and is referenced solely in `dashboard/src/lib/apiProxy.ts`. | **VERIFIED.** Inspected bundled JS and webpack assets; zero tokens in client-accessible bundles. |
| **Proxy Header Injection** | `prepareProxyHeaders()` injects `X-API-Key: ${process.env.API_AUTH_TOKEN}` on upstream requests. | **VERIFIED.** Tested against FastAPI backend requiring `API_AUTH_TOKEN="secret-review-token-123"`; requests succeed with 200 OK. |
| **Client Tampering Immunity** | `prepareProxyHeaders()` strictly overrides incoming client `x-api-key` and suppresses client `Authorization` headers when server token is configured. | **VERIFIED.** Tested in proxy unit test suite (Tests 5, 21). |
| **Fail-Closed Missing Token** | If `API_AUTH_TOKEN` is unset on the frontend proxy, requests forward without credentials. | **VERIFIED.** FastAPI `verify_api_key` rejects protected endpoints with `401 Unauthorized` while allowing public `/api/status`. |
| **Image Secret Cleanliness** | Docker layer history and inspect output. | **VERIFIED.** `docker history` and `docker inspect` show no secrets baked into image layers or build args. |
| **Error Information Leakage** | Proxy catches upstream failures (e.g. `ECONNREFUSED`) and emits sanitized JSON. | **VERIFIED.** Returns `{ success: false, error: "Backend service unreachable" }` (502). Zero connection strings or internal IPs exposed. |

---

## 4. Container Networking & Topology

### 4.1 Topology Requirements
In a multi-container Docker environment, the containers must be attached to a **user-defined network** (e.g. `docker network create bi-network` or a Docker Compose network):
- **Why default bridge fails:** Docker's default bridge network (`bridge`) does not provide automatic DNS resolution between container names. Calling `http://test-backend:8000` on the default bridge fails with `getaddrinfo ENOTFOUND`.
- **User-defined bridge success:** On a custom network, Docker's embedded DNS server (`127.0.0.11`) automatically resolves container names.

### 4.2 Localhost vs Container Hostnames
- **Frontend Upstream Configuration:** In container deployments, `API_INTERNAL_URL` must be explicitly configured to the backend container name (e.g. `http://bi-api:8000` or `http://bi-api-service:8000`). If omitted, `getBackendBaseUrl()` falls back to `http://127.0.0.1:8000`, which refers to the frontend container's own loopback interface, failing with `502 Bad Gateway`.
- **Database Configuration:** In container deployments, `DATABASE_URL` must use the PostgreSQL container name (e.g. `postgresql://user:pass@postgres:5432/db`), not `localhost:5432`.
- **Browser-Side Requests:** Browser client calls use relative URLs (`/api/businesses`), resolving against the browser origin, which routes through the Next.js server proxy. This correctly avoids browser resolution of internal container hostnames.

---

## 5. Database Access & Persistence Audit

### 5.1 Verification of Persistence Ownership
- **FastAPI Backend:** Primary owner of all business logic, scraper execution, database mutations, and API endpoints. Reads and writes via `ScraperRepository` in `database/db.py`.
- **Next.js Frontend:** Owns read-only queries during server-side initial rendering. Possesses no mutation endpoints touching PostgreSQL directly.

### 5.2 The Fresh Database Schema Blocker
During live topology testing against a clean `postgres:15-alpine` container without pre-initialized tables:
```
psycopg2.errors.UndefinedTable: relation "businesses" does not exist
LINE 32: FROM businesses b
```
- **Root Cause:** In Phase 5C, automatic execution of `schema.sql` on server startup was removed to prevent multi-worker DDL contention and startup latency. The backend assumes the database schema is already initialized.
- **Verification:** When `database/schema.sql` was mounted into `/docker-entrypoint-initdb.d/init.sql` (or executed prior to backend startup), `/api/businesses` immediately returned `{"success":true,"businesses":[],"limit":null,"offset":0}` with HTTP `200 OK`.
- **Requirement:** Any fresh deployment must include a schema migration or initialization step.

---

## 6. CI/CD Pipeline & Test Coverage Audit

### 6.1 GitHub Actions Workflow (`.github/workflows/ci.yml`)
The current workflow comprises four jobs:
1. `test-offline`: Runs 424 Python unit and offline tests, validates Kubernetes Kustomize manifests. Completely isolated from database.
2. `test-postgres-integration`: Runs service-backed PostgreSQL integration tests against `postgres:15-alpine`.
3. `docker-build`: Installs dependencies, builds `business-intelligence-api:ci`, and runs 8 backend container deployment smoke tests (`pytest -m "docker"`).
4. `frontend-build`: Installs Node 20 dependencies via `npm ci`, runs 23 proxy unit tests (`npm test`), runs Next.js production build (`npm run build`), builds the frontend image (`business-intelligence-frontend:ci`), and runs the container smoke test (`npm run test:smoke`).

### 6.2 Test Coverage Analysis
- **Does the smoke test exercise the final image?**
  **YES.** `dashboard/tests/containerSmoke.test.mjs` starts a real container from `FRONTEND_IMAGE_TAG` (`business-intelligence-frontend:ci`), tests HTTP `200` on root, verifies non-root user `nextjs` (UID 1001), asserts `.git` and `.env` exclusion, and validates proxy fail-closed behavior.
- **Identified Integration Gap:**
  CI currently tests the backend container in isolation (`docker-build`) and the frontend container in isolation (`frontend-build`). There is no multi-container integration job that runs Frontend + Backend + PostgreSQL concurrently in CI.

---

## 7. Blockers & Risks Ranked by Severity

| Blocker ID | Severity | Category | Description | Mitigation / Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **BLK-01** | **Medium-High** | Database Schema | Clean PostgreSQL instances lack tables. Without pre-running `database/schema.sql`, backend `/api/businesses` returns 500 (`relation "businesses" does not exist`). | Automated initialization step: run `database/schema.sql` via entrypoint or init container before starting application containers. |
| **BLK-02** | **Medium** | Architecture | Split data architecture: SSR pages directly connect to PostgreSQL, while interactive client operations use the API proxy. If `DATABASE_URL` is missing on the frontend container, SSR renders mock data before client hydration. | Pass `DATABASE_URL` to both frontend and backend containers in local deployment, or refactor SSR to fetch from internal API in a future phase. |
| **BLK-03** | **Medium** | Networking | Running containers on default bridge without a user-defined network breaks container name DNS resolution (`getaddrinfo ENOTFOUND`). | Require user-defined bridge network (`docker network create`) or Docker Compose for local multi-container runs. |
| **BLK-04** | **Low-Medium** | Configuration | `API_INTERNAL_URL` defaults to `http://127.0.0.1:8000`, which refers to the frontend container's loopback interface, failing immediately with 502 across containers if omitted. | Explicitly configure `API_INTERNAL_URL` in container environment and deployment documentation. |
| **BLK-05** | **Low** | CI Coverage | CI validates containers in isolation; no remote CI test exercises multi-container communication. | Add a service-backed multi-container integration test in CI once orchestration manifests are stabilized. |

---

## 8. Minimal Recommended Next Steps

1. **Local Multi-Container Deployment (Immediate):**
   Provide a standard local orchestration (e.g. a clean `deploy/docker-compose.yaml` or runbook) that:
   - Creates a user-defined bridge network.
   - Spins up PostgreSQL with `database/schema.sql` auto-mounted in `/docker-entrypoint-initdb.d/`.
   - Spins up `business-intelligence-api` with `DATABASE_URL` and `API_AUTH_TOKEN`.
   - Spins up `business-intelligence-frontend` with `API_INTERNAL_URL`, `API_AUTH_TOKEN`, and `DATABASE_URL`.
2. **Kubernetes Frontend Manifests (Phase 6I):**
   Generate `deploy/kubernetes/frontend-deployment.yaml`, `frontend-service.yaml`, and update `kustomization.yaml` to deploy both tiers into the Kubernetes cluster.
3. **Commit & Push Phase 6G / 6H Changes:**
   Commit the validated Dockerfile, `.dockerignore`, smoke tests, and CI workflow updates to trigger remote GitHub Actions.

---

## 9. Verification Log & Exact Test Results

### 9.1 Live Integrated 3-Container Test Run
Executed command:
```bash
docker network create test-bi-net
docker run -d --name test-postgres --network test-bi-net \
  -e POSTGRES_USER=testuser -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=testdb \
  -v "$PWD/database/schema.sql:/docker-entrypoint-initdb.d/init.sql" postgres:15-alpine
docker run -d --name test-backend --network test-bi-net \
  -e API_AUTH_TOKEN="secret-review-token-123" \
  -e DATABASE_URL="postgresql://testuser:testpass@test-postgres:5432/testdb" \
  business-intelligence-api:ci
docker run -d --name test-frontend --network test-bi-net -p 3015:3000 \
  -e PORT=3000 -e HOSTNAME=0.0.0.0 \
  -e API_INTERNAL_URL="http://test-backend:8000" \
  -e API_AUTH_TOKEN="secret-review-token-123" \
  business-intelligence-frontend:test
```
**Results:**
- `GET http://127.0.0.1:3015/` -> `HTTP 200 OK` (Next.js SSR rendered)
- `GET http://127.0.0.1:3015/api/status` -> `HTTP 200 OK`:
  `{"success":true,"is_running":false,"running_process":false}`
- `GET http://127.0.0.1:3015/api/businesses` -> `HTTP 200 OK`:
  `{"success":true,"businesses":[],"limit":null,"offset":0}`
- `GET http://127.0.0.1:3015/api/health/ready` -> `HTTP 200 OK`:
  `{"status":"ready","mode":"connected","components":{"database":{"status":"connected"}}}`

### 9.2 Frontend Unit & Container Smoke Tests
- Frontend Proxy Tests: `23 passed in 167ms`
- Frontend Container Pytest: `4 passed in 1.62s`
- Backend Container Pytest: `8 passed in 1.98s`
- Kubernetes Manifest Tests: `12 passed in 0.17s`
- Python Offline Unit Tests: `424 passed, 13 deselected in 6.50s`

---

## 10. Git Working-Tree Status

Changes remain uncommitted and unpushed:

```
Changes not staged for commit:
	modified:   .github/workflows/ci.yml
	modified:   dashboard/README.md
	modified:   dashboard/next.config.ts
	modified:   dashboard/package.json

Untracked files:
	AI_MEMORY/PHASE_6G_FRONTEND_CONTAINERIZATION.md
	AI_MEMORY/PHASE_6H_INTEGRATED_DEPLOYMENT_READINESS.md
	dashboard/.dockerignore
	dashboard/Dockerfile
	dashboard/tests/containerSmoke.test.mjs
	tests/test_frontend_container_smoke.py
```
