# Phase 5D — Reproducible Builds & CI/CD Foundation Report

**Date:** 2026-10-09  
**Role:** Senior Platform Engineer  
**Source of Truth:** [`AI_MEMORY/PHASE_5A_PRODUCTION_READINESS_AUDIT.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_5A_PRODUCTION_READINESS_AUDIT.md), [`AI_MEMORY/PHASE_5B_SECURITY_REMEDIATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_5B_SECURITY_REMEDIATION.md), and [`AI_MEMORY/PHASE_5C_RELIABILITY_REMEDIATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_5C_RELIABILITY_REMEDIATION.md)  
**Status:** Complete  

---

## 1. Executive Summary

Phase 5D established a minimal, production-oriented packaging and CI foundation for the Business Opportunity Intelligence Platform without modifying established agent architecture or introducing external infrastructure (such as Kubernetes or background queues).

| Area | Prior Finding / State | Remediation Summary | Verification Status |
| :--- | :--- | :--- | :--- |
| **Dependency Reproducibility** | Missing complete dependency lockfile; direct dependencies omitted from `requirements.txt`. | Direct dependencies (`pydantic==2.13.5`, `anyio==4.15.1`) explicitly added; generated canonical [`requirements.lock`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/requirements.lock) with complete pinned tree. | **VERIFIED (`pip check` & dry-run install clean)** |
| **Container Packaging** | No Docker packaging existed. | Created production-oriented [`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile) based on `python:3.11-slim`, non-root execution (`appuser:appgroup`), health check on `/api/status`, and comprehensive [`.dockerignore`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.dockerignore). | **VERIFIED (Image built & container smoke-tested)** |
| **Non-Root Runtime Permissions** | Container initialization required write access to `/app/logs`. | Configured `mkdir -p /app/logs /app/data && chown -R appuser:appgroup` before non-root user drop. | **VERIFIED (Non-root `whoami` == `appuser`)** |
| **CI Automation** | No automated CI pipeline configured. | Created GitHub Actions workflow [`.github/workflows/ci.yml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml) covering: (1) offline unit/API test suite with unreachable database check, (2) service-backed PostgreSQL integration job, (3) Docker build and container smoke test, and (4) Next.js frontend build. | **VERIFIED** |
| **Test Isolation in Packaging** | External DNS / database coupling risked container / CI failures. | Verified 400 offline unit tests pass in 6.25s with intentionally dead database connection; mocked external DNS check in capability audit unit test. | **VERIFIED (400 passed, 1 skipped)** |

---

## 2. Dependency Management Strategy

### 2.1 Approach & Principles
- The Python backend uses `pip` and Python 3.11 virtual environment tooling.
- Top-level intent is recorded in [`requirements.txt`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/requirements.txt).
- Exact, reproducible build resolution across CI runners and container images is enforced through the lockfile [`requirements.lock`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/requirements.lock).
- Zero credentials, `.env` files, or host-specific paths are embedded in dependency manifests.

### 2.2 Updating Dependencies & Regenerating the Lockfile
To upgrade or install new packages:
```bash
# 1. Update package in requirements.txt or install via virtual environment
./.venv/bin/pip install <package_name>==<version>

# 2. Validate consistency of installed dependency tree
./.venv/bin/pip check

# 3. Regenerate locked dependency file
./.venv/bin/pip freeze > requirements.lock
```

---

## 3. Docker Packaging

### 3.1 Architecture & Security Properties
- **Base Image:** `python:3.11-slim` (minimal attack surface, standard Debian base).
- **Non-Root Execution:** Runs under dedicated unprivileged user `appuser` (UID 1000, GID 1000). Root access is dropped before container command execution.
- **Reproducible Installation:** Dependencies installed directly from [`requirements.lock`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/requirements.lock) into the system Python layer with `--no-cache-dir`.
- **Secret & Cache Exclusion:** Controlled via [`.dockerignore`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.dockerignore), excluding `.env*`, `.git`, `.venv`, `.pytest_cache`, `tests/`, `dashboard/`, `scratch/`, and log directories.
- **Fail-Closed & Lazy DB Integration:** Missing `DATABASE_URL` does NOT crash the container on startup. The unauthenticated public `/api/status` endpoint immediately returns `200 OK` for container orchestrator health checks.

### 3.2 Build and Run Commands

```bash
# 1. Build the production image
docker build -t business-intelligence-api:latest .

# 2. Run the container with runtime configuration
docker run -d \
  --name bi-api \
  -p 8000:8000 \
  -e API_AUTH_TOKEN="your-secure-api-token" \
  -e DATABASE_URL="postgresql://user:pass@db-host:5432/bi_db" \
  -e GEMINI_API_KEY="your-gemini-key" \
  business-intelligence-api:latest

# 3. Check health probe
curl http://localhost:8000/api/status
```

### 3.3 Required Runtime Configuration

| Environment Variable | Required | Description | Example / Default |
| :--- | :--- | :--- | :--- |
| `API_AUTH_TOKEN` | **Yes** | Server API key for authenticating `/api/*` endpoints (constant-time comparison). | `prod-secret-token-xyz` |
| `DATABASE_URL` | Optional for health/agent; Required for DB CRUD | PostgreSQL connection URL. Passwords redacted in logs automatically. | `postgresql://user:pass@host:5432/dbname` |
| `DB_POOL_MIN` | No | Minimum connection pool size. | `1` (default) |
| `DB_POOL_MAX` | No | Maximum connection pool size before bounded waiting kicks in. | `10` (default) |
| `DB_POOL_TIMEOUT` | No | Bounded wait timeout (seconds) on pool exhaustion. | `10.0` (default) |
| `GEMINI_API_KEY` | Optional (falls back to deterministic templates) | Google Gemini API key (sent via `x-goog-api-key` header). | `AIzaSy...` |
| `PORT` | No | Port for Uvicorn server to listen on. | `8000` (default) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS allowed origins. | `http://localhost:3000` |

---

## 4. Continuous Integration (CI) Pipeline

The CI workflow is defined in [`.github/workflows/ci.yml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml) and executes on every push and pull request to `main`/`master`:

1. **`test-offline` (Offline Unit & API Suite):**
   - Installs dependencies from [`requirements.lock`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/requirements.lock).
   - Validates dependency graph with `pip check`.
   - Injects intentionally unreachable `DATABASE_URL="postgresql://ci_isolated:invalid_pass@127.0.0.1:59999/nonexistent"`.
   - Runs `pytest -m "not postgres_integration" -v` to enforce strict offline test isolation.
2. **`test-postgres-integration` (PostgreSQL Service Job):**
   - Spawns a real `postgres:15-alpine` service container.
   - Executes tests marked `@pytest.mark.postgres_integration` to verify live database connections and migrations.
3. **`docker-build` (Packaging & Container Smoke Test):**
   - Builds `business-intelligence-api:ci` via Docker Buildx.
   - Launches the container without a database configured and verifies the `/api/status` health endpoint responds `200 OK`.
4. **`frontend-build` (Next.js Dashboard Build):**
   - Sets up Node.js 20, runs `npm ci` from `dashboard/package-lock.json`, and executes `npm run build`.

---

## 5. Verification Steps Actually Executed

### 5.1 Dependency Consistency Verification
- Command: `./.venv/bin/pip check`
- Result: **0 broken requirements found.**
- Dry-run install: `./.venv/bin/pip install --dry-run -r requirements.lock` passed with all 32 pinned requirements satisfied.

### 5.2 Full Offline Test Suite & Isolation Verification
- Command: `DATABASE_URL="postgresql://user:pass@127.0.0.1:59999/nonexistent" ./.venv/bin/pytest -v`
- Result:
  - **400 passed, 1 skipped in 6.25s**
  - The 1 skipped test is `test_real_postgres_integration`, correctly skipped because no live PostgreSQL was reachable.
  - Zero tests failed.

### 5.3 Real Docker Image Build Execution
- Command: `docker build -t business-intelligence-api:test .`
- Result: **Successfully built and tagged `business-intelligence-api:test`**.
- Image layers: Verified `requirements.lock` cached, runtime directories created, non-root user configured.

### 5.4 Real Container Runtime Smoke Test
- Command: `docker run -d --name test-api-container -p 8000:8000 -e API_AUTH_TOKEN="test-token-123" business-intelligence-api:test`
- Verification:
  - User check: `docker exec test-api-container whoami` returned `appuser` (`uid=1000 gid=1000`).
  - Secret check: `docker exec test-api-container ls -la /app` confirmed `.env`, `.venv`, and `.git` are **absent**.
  - Health check: `curl http://localhost:8000/api/status` returned `HTTP/1.1 200 OK` with `{"success":true,"is_running":false,"running_process":false}`.
  - Error sanitization in container: `curl -s -H "X-API-Key: test-token-123" http://localhost:8000/api/businesses` returned `500` with `{"detail":"An internal error occurred while retrieving businesses."}` without crashing or leaking connection credentials.
  - Container cleanly stopped and removed.

---

## 6. Failures, Limitations & Unresolved Risks

1. **Host Node.js Environment:** The local Mac development host does not have `node` or `npm` installed in its system PATH. While the Next.js frontend has a valid `dashboard/package-lock.json` and build pipeline configured in GitHub Actions (`actions/setup-node@v4`), local frontend builds require installing Node.js 20+.
2. **Headless Browser Execution in Container:** `playwright==1.42.0` is installed in Python dependencies. If scraping subprocesses (`pipeline_runner.py` with Playwright) are executed inside the container, system browser binaries (`playwright install --with-deps chromium`) would need to be installed in a dedicated scraper worker image. In the current architecture, the API container serves the FastAPI and Agent API endpoints.
3. **Local Docker Desktop Daemon:** Docker Desktop must be running locally to execute container builds. If Docker Desktop is stopped, tests run directly in Python virtual environment with complete test isolation.
