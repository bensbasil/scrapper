# Phase 6I-A — Reproducible Local Multi-Container Deployment

**Date:** 2026-10-11  
**Role:** Senior Platform Engineer  
**Scope:** Reproducible Docker Compose multi-container deployment orchestrating PostgreSQL (`postgres`), FastAPI backend (`backend`), and Next.js frontend (`frontend`) with persistent storage and automatic schema initialization.  
**Status:** **COMPLETE & VERIFIED** (Compose configuration validated, complete stack launched and tested end-to-end, fresh volume schema init verified, volume persistence across restarts verified, volume wipe behavior verified, 23 proxy tests passed, 424 Python unit tests passed)

---

## 1. Executive Summary & Developer Usability

### Can a developer start the entire application from a clean checkout?
**YES, UNCONDITIONALLY.**

From a clean checkout with Docker installed, a developer can run a single command from the repository root:
```bash
docker compose -f deploy/docker-compose.yaml up -d --build
```
Compose executes a fully ordered startup sequence:
1. Creates the isolated user-defined bridge network (`bi_network`) and named persistent volume (`bi_postgres_data`).
2. Starts `postgres:15-alpine` and automatically initializes all 19 database tables from [`database/schema.sql`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/schema.sql) on first boot.
3. Waits for PostgreSQL's `pg_isready` health check to pass.
4. Builds and starts `business-intelligence-api:local` (FastAPI backend), automatically wiring the connection to `postgres:5432` with `API_AUTH_TOKEN`.
5. Waits for the backend liveness probe (`/api/health/live`) to pass.
6. Builds and starts `business-intelligence-frontend:local` (Next.js standalone frontend), automatically wiring `API_INTERNAL_URL="http://backend:8000"`, `API_AUTH_TOKEN`, and `DATABASE_URL`.
7. Waits for frontend liveness (`wget --spider http://127.0.0.1:3000/`) to pass.

The entire application is immediately reachable at:
- **Dashboard UI:** `http://localhost:3000`
- **Backend API:** `http://localhost:8000`

---

## 2. Architecture & Service Topology

```
+-----------------------------------------------------------------------------------------+
| DOCKER BRIDGE NETWORK: bi_network                                                       |
|                                                                                         |
|  +--------------------+         +--------------------+         +---------------------+  |
|  | postgres           | <------ | backend            | <------ | frontend            |  |
|  | (bi-postgres)      |         | (bi-backend)       |         | (bi-frontend)       |  |
|  | Image: 15-alpine   |         | Image: api:local   |         | Image: fe:local     |  |
|  | Port: 5432         |         | Port: 8000         |         | Port: 3000          |  |
|  | Volume: data       |         | Health: /health    |         | Health: /           |  |
|  | Init: schema.sql   |         | User: appuser      |         | User: nextjs        |  |
|  +--------------------+         +--------------------+         +---------------------+  |
|            ^                                                              |             |
|            +--------------------------------------------------------------+             |
|                                 (Direct SSR read query)                                 |
+-----------------------------------------------------------------------------------------+
                                             |                              |
                                  Host Port: 8000                Host Port: 3000
```

### 2.1 Services Specification

1. **`postgres` (`bi-postgres`):**
   - **Image:** `postgres:15-alpine`
   - **Persistent Storage:** Named volume `postgres_data` mapped to `/var/lib/postgresql/data`.
   - **Schema Initialization:** `database/schema.sql` mounted read-only to `/docker-entrypoint-initdb.d/01_schema.sql:ro`. Executes automatically on clean initialization of an empty data directory.
   - **Healthcheck:** `pg_isready -U ${POSTGRES_USER:-bi_user} -d ${POSTGRES_DB:-bi_db}` with 5s interval, 5s timeout, 5 retries.
2. **`backend` (`bi-backend`):**
   - **Build:** `context: ..`, `dockerfile: Dockerfile`.
   - **Security:** Runs as non-root user `appuser` (UID 1000).
   - **Dependency Management:** `depends_on: postgres: condition: service_healthy`.
   - **Environment:**
     - `DATABASE_URL: postgresql://${POSTGRES_USER:-bi_user}:${POSTGRES_PASSWORD:-bi_password}@postgres:5432/${POSTGRES_DB:-bi_db}`
     - `API_AUTH_TOKEN: ${API_AUTH_TOKEN:-dev-secret-token-change-in-prod}`
     - `PORT: 8000`
     - `ALLOWED_ORIGINS: http://localhost:3000,http://127.0.0.1:3000,http://frontend:3000`
   - **Healthcheck:** `curl -f http://localhost:8000/api/health/live || exit 1`.
3. **`frontend` (`bi-frontend`):**
   - **Build:** `context: ../dashboard`, `dockerfile: Dockerfile`.
   - **Security:** Runs as non-root user `nextjs` (UID 1001).
   - **Dependency Management:** `depends_on: backend: condition: service_healthy, postgres: condition: service_healthy`.
   - **Environment:**
     - `PORT: 3000`, `HOSTNAME: 0.0.0.0`
     - `API_INTERNAL_URL: http://backend:8000`
     - `API_AUTH_TOKEN: ${API_AUTH_TOKEN:-dev-secret-token-change-in-prod}`
     - `DATABASE_URL: postgresql://${POSTGRES_USER:-bi_user}:${POSTGRES_PASSWORD:-bi_password}@postgres:5432/${POSTGRES_DB:-bi_db}`
   - **Healthcheck:** `wget -q --spider http://127.0.0.1:3000/ || exit 1`.

---

## 3. Key Design Decisions

### 3.1 Decision on Frontend `DATABASE_URL`
The Phase 6H audit revealed that React Server Components in Next.js (`page.tsx`, `runs/page.tsx`, `business/[id]/page.tsx`) execute direct read queries via `pg.Pool` during initial SSR page load. 
- **Decision:** `DATABASE_URL` is passed directly to the frontend container in `deploy/docker-compose.yaml`.
- **Rationale:** 
  - Allows React Server Components to render live database records directly in initial HTML before client hydration.
  - Prevents pages from falling back to mock data or rendering empty run lists.
  - Completely preserves the existing application architecture without requiring invasive code refactoring or microservice redesign.
  - Interactive client actions (scraping, stopping, updating status, SSE log streaming) continue to route exclusively through the server-side API proxy to FastAPI.

### 3.2 Decision on Database Schema Initialization
- **Problem:** In Phase 5C, automatic execution of DDL on application startup was decoupled to prevent DDL deadlocks and startup latency. Fresh PostgreSQL instances lacked tables, causing 500 errors on `/api/businesses`.
- **Solution:** Mounted `database/schema.sql` into `/docker-entrypoint-initdb.d/01_schema.sql:ro`. Official PostgreSQL images execute scripts in this directory automatically during empty data directory initialization.
- **Result:** Fresh volumes create all 19 relational tables before backend and frontend containers start.

### 3.3 Decision on Volume Persistence vs Reset
- Standard `docker compose down` halts and removes containers and networks but **retains the named volume `bi_postgres_data`**.
- Resetting the database to an empty slate (re-triggering `schema.sql`) is executed intentionally via `docker compose down -v`.

---

## 4. Verification and Validation Results

### 4.1 Configuration Validation
Executed command: `docker compose -f deploy/docker-compose.yaml config`
**Result:** **Exit code 0**; valid Compose YAML parsed with default development environment interpolation.

### 4.2 Stack Launch and Health Validation
Executed command: `docker compose -f deploy/docker-compose.yaml up -d --build`
```
NAME          IMAGE                                  COMMAND                  SERVICE    STATUS
bi-postgres   postgres:15-alpine                     "docker-entrypoint.s…"   postgres   Up 17s (healthy)
bi-backend    business-intelligence-api:local        "uvicorn api_server:…"   backend    Up 12s (healthy)
bi-frontend   business-intelligence-frontend:local   "docker-entrypoint.s…"   frontend   Up 6s (healthy)
```
**Result:** All three containers transitioned to `healthy` within 18 seconds.

### 4.3 Endpoint Verification
Executed against the running Compose deployment:
1. **Frontend HTTP Root:**
   `curl -I http://127.0.0.1:3000/` -> `HTTP/1.1 200 OK`
2. **Public API Proxy Route:**
   `curl -s http://127.0.0.1:3000/api/status` -> `{"success":true,"is_running":false,"running_process":false}`
3. **Protected API Proxy Route:**
   `curl -s http://127.0.0.1:3000/api/businesses` -> `{"success":true,"businesses":[],"limit":null,"offset":0}`
4. **Backend Direct Health Readiness:**
   `curl -s http://127.0.0.1:8000/api/health/ready` -> `{"status":"ready","mode":"connected","components":{"database":{"status":"connected"}}}`
5. **Frontend SSR Runs Page:**
   `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/runs` -> `200`
6. **PostgreSQL Schema Inspection:**
   `docker exec bi-postgres psql -U bi_user -d bi_db -c '\dt'` -> Verified all 19 tables (`businesses`, `scoring_results`, `change_events`, `company_registry`, `decision_makers`, `outreach_drafts`, `pipeline_runs`, `tech_stacks`, `website_analyses`, etc.) initialized and owned by `bi_user`.

### 4.4 Volume Persistence Across Restarts
1. Inserted record: `INSERT INTO businesses (business_name, category) VALUES ('Persistence Test Corp', 'Technology');`
2. Stopped stack: `docker compose -f deploy/docker-compose.yaml down` (without `-v`)
3. Restarted stack: `docker compose -f deploy/docker-compose.yaml up -d`
4. Queried `/api/businesses` through frontend proxy:
   `{"success":true,"businesses":[{"id":"1","business_name":"Persistence Test Corp","category":"Technology",...}]}`
**Result:** Persistent volume `bi_postgres_data` retained application data across complete shutdown and restart.

### 4.5 Volume Wipe & Clean Reinitialization
1. Stopped stack with volume removal: `docker compose -f deploy/docker-compose.yaml down -v`
2. Restarted stack: `docker compose -f deploy/docker-compose.yaml up -d`
3. Queried `/api/businesses` through frontend proxy:
   `{"success":true,"businesses":[],"limit":null,"offset":0}`
**Result:** Fresh volume created, `database/schema.sql` automatically re-executed, clean database established.

### 4.6 Regression Suite Results
- Frontend proxy unit tests (`npm test`): **23 passed in 151ms**
- Python offline test suite (`pytest -m "not postgres_integration and not docker"`): **424 passed, 13 deselected in 7.77s**
- Kubernetes manifest test suite (`pytest tests/test_kubernetes_manifests.py`): **12 passed in 0.08s**

---

## 5. Files Changed and Created

| File Path | Action | Description |
| :--- | :--- | :--- |
| [`deploy/docker-compose.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/docker-compose.yaml) | Created | Multi-container Docker Compose file orchestrating PostgreSQL, FastAPI, and Next.js frontend with networking, health checks, and volume mounts. |
| [`deploy/.env.example`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/.env.example) | Created | Example environment file with safe placeholder variables for Compose deployment. |
| [`.env.example`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.env.example) | Created | Root template for local development and Docker Compose. |
| [`deploy/README.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/README.md) | Created | Runbook documenting Compose startup, status verification, logging, smoke testing, and database reset commands. |
| [`.gitignore`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.gitignore) | Modified | Added exceptions (`!.env.example`, `!deploy/.env.example`) allowing documentation templates to be tracked while keeping credentials excluded. |

---

## 6. Known Limitations & Next Steps

1. **In-Container Browser Scraping:** In-container Playwright browser scraping remains disabled in the FastAPI container; full headless browser execution will be handled in a dedicated scraper worker image in future phases.
2. **Kubernetes Frontend Manifests (Phase 6I-B / 6J):** Kubernetes manifests currently exist only for the backend API in `deploy/kubernetes/`. Frontend Kubernetes Deployment and Service manifests will be introduced in the next phase.
3. **Commit & Push:** All changes remain uncommitted and unpushed in the local working tree per constraints.

---

## 7. Git Working-Tree Status

```
Changes not staged for commit:
	modified:   .github/workflows/ci.yml
	modified:   .gitignore
	modified:   dashboard/README.md
	modified:   dashboard/next.config.ts
	modified:   dashboard/package.json

Untracked files:
	.env.example
	AI_MEMORY/PHASE_6G_FRONTEND_CONTAINERIZATION.md
	AI_MEMORY/PHASE_6H_INTEGRATED_DEPLOYMENT_READINESS.md
	AI_MEMORY/PHASE_6I_A_LOCAL_DEPLOYMENT.md
	dashboard/.dockerignore
	dashboard/Dockerfile
	dashboard/tests/containerSmoke.test.mjs
	deploy/.env.example
	deploy/README.md
	deploy/docker-compose.yaml
	tests/test_frontend_container_smoke.py
```
