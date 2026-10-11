# Phase 6G — Production Container Packaging for Next.js Dashboard

**Date:** 2026-10-11  
**Role:** Senior Platform Engineer  
**Scope:** Production containerization, multi-stage Docker build, standalone output optimization, non-root execution, container deployment smoke testing, and CI pipeline integration for the Next.js frontend dashboard (`dashboard/`).  
**Status:** **COMPLETE & VERIFIED** (Multi-stage image built, 73.9 MB content size, 4/4 container smoke tests passed, 23/23 frontend proxy tests passed, Next.js build clean, 424 Python unit tests passed, 8 backend container tests intact)

---

## 1. Executive Summary & Architecture

Phase 6G packages the Next.js dashboard into an optimized, secure, production-ready container image designed to run independently in containerized and Kubernetes environments while securely communicating with the FastAPI backend through the server-side API proxy.

### Image Architecture Overview

```
+----------------------------------------------------------------------------------+
| MULTI-STAGE DOCKER BUILD (dashboard/Dockerfile)                                  |
|                                                                                  |
|  [Stage 1: base] node:20-alpine                                                 |
|    - Alpine Linux with libc6-compat                                              |
|                                                                                  |
|  [Stage 2: deps]                                                                 |
|    - COPY package.json package-lock.json                                         |
|    - RUN npm ci (reproducible dependency tree)                                  |
|                                                                                  |
|  [Stage 3: builder]                                                              |
|    - COPY --from=deps /app/node_modules ./node_modules                           |
|    - COPY . . (dev files filtered by .dockerignore)                              |
|    - RUN npm run build (produces Next.js standalone output in .next/standalone)  |
|                                                                                  |
|  [Stage 4: runner (Production Image)]                                            |
|    - Dedicated non-root user: nextjs (UID 1001, GID 1001)                        |
|    - COPY --from=builder /app/public ./public                                    |
|    - COPY --from=builder /app/.next/standalone ./                                |
|    - COPY --from=builder /app/.next/static ./.next/static                        |
|    - EXPOSE 3000                                                                 |
|    - HEALTHCHECK CMD wget -q --spider http://127.0.0.1:3000/ || exit 1          |
|    - CMD ["node", "server.js"]                                                   |
+----------------------------------------------------------------------------------+
```

### Key Architectural Highlights
1. **Next.js Standalone Output:** Configured `output: "standalone"` in [`dashboard/next.config.ts`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/next.config.ts). Next.js automatically bundles only the necessary `node_modules` and server code required to serve the application via `node server.js`, discarding developer dependencies (TypeScript, Tailwind PostCSS, ESLint).
2. **Minimal Runtime Footprint:** The final image content size is **73.9 MB** (compressed download ~40 MB), enabling rapid pod startup and minimal container registry storage.
3. **Non-Root Execution:** Runs under the unprivileged `nextjs` user (`UID 1001`, `GID 1001`). Root access is strictly dropped.
4. **Zero Secret Baking:** `API_INTERNAL_URL` and `API_AUTH_TOKEN` are read at runtime via standard server-side environment variables. Neither secret is defined as a `NEXT_PUBLIC_` variable or baked into build layers, image arguments, or static client bundles.
5. **Strict File Isolation:** [`dashboard/.dockerignore`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/.dockerignore) excludes `.git`, `.env*`, `node_modules`, `tests/`, and build artifacts from the image.

---

## 2. Runtime Configuration

The container is configured at runtime via standard environment variables:

| Variable | Required | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `PORT` | Optional | `3000` | HTTP port the standalone Next.js server binds to. |
| `HOSTNAME` | Optional | `0.0.0.0` | Bind address (must be `0.0.0.0` inside container to accept forwarded traffic). |
| `API_INTERNAL_URL` | Optional | `http://127.0.0.1:8000` | Upstream FastAPI backend base URL (e.g. `http://bi-api-service:8000` in Kubernetes). |
| `API_AUTH_TOKEN` | Recommended | *None* | Shared secret injected into upstream requests by the server-side proxy (`X-API-Key`). Never sent to browser clients. |
| `DATABASE_URL` | Optional | *None* | PostgreSQL connection string for server-side queries. Safely falls back if unconfigured. |

---

## 3. Files Changed and Created

| File Path | Action | Description |
| :--- | :--- | :--- |
| [`dashboard/Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/Dockerfile) | Created | Multi-stage, Alpine-based production Dockerfile with non-root user, standalone packaging, and health check. |
| [`dashboard/.dockerignore`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/.dockerignore) | Created | Excludes `node_modules`, `.next`, `.env*`, `.git`, `tests/`, and documentation from build context. |
| [`dashboard/next.config.ts`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/next.config.ts) | Modified | Added `output: "standalone"` to enable Next.js minimal standalone deployment mode. |
| [`dashboard/package.json`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/package.json) | Modified | Added `"test:smoke": "node --test tests/containerSmoke.test.mjs"` script. |
| [`dashboard/tests/containerSmoke.test.mjs`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/tests/containerSmoke.test.mjs) | Created | Node.js deployment smoke test suite verifying container startup, root HTTP 200, non-root user, secret exclusion, proxy 502 fail-closed, and clean shutdown. |
| [`tests/test_frontend_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_frontend_container_smoke.py) | Created | Pytest container deployment smoke test suite marked with `@pytest.mark.docker` for automated pytest execution. |
| [`.github/workflows/ci.yml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml) | Modified | Updated `frontend-build` job to build the Docker image and execute `npm run test:smoke`. |
| [`dashboard/README.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/README.md) | Modified | Added "Production Container Packaging (Phase 6G)" section with build, run, and testing instructions. |

---

## 4. Test Execution & Verification Results

### 4.1 Frontend Proxy Automated Unit Tests
Executed command: `docker run --rm -v "$PWD/dashboard:/app" -w /app node:20 npm test`
```
TAP version 13
ok 1 - getBackendBaseUrl defaults to http://127.0.0.1:8000
ok 2 - getBackendBaseUrl prioritizes API_INTERNAL_URL and strips trailing slashes
ok 3 - buildTargetUrl constructs target URL preserving subpaths and query params
ok 4 - prepareProxyHeaders injects server-side API_AUTH_TOKEN as X-API-Key
ok 5 - prepareProxyHeaders server token overrides client-supplied X-API-Key
ok 6 - prepareProxyHeaders passes client key when server token is unconfigured
ok 7 - prepareProxyHeaders leaves X-API-Key unset when neither server nor client provides one
ok 8 - filterResponseHeaders strips hop-by-hop headers
ok 9 - handleApiProxy proxies GET /api/businesses with query and server auth
ok 10 - handleApiProxy proxies POST /api/scrape with JSON payload
ok 11 - handleApiProxy proxies PATCH /api/businesses/:id with status update
ok 12 - handleApiProxy proxies DELETE /api/businesses correctly
ok 13 - handleApiProxy preserves SSE streaming for /api/logs
ok 14 - handleApiProxy forwards 401 Unauthorized when backend rejects credentials
ok 15 - handleApiProxy returns 502 Bad Gateway when backend is completely unreachable
ok 16 - buildTargetUrl rejects path traversal sequences (.., ., %2e%2e, /, \)
ok 17 - handleApiProxy returns 400 Bad Request on path traversal attempts
ok 18 - filterResponseHeaders strips content-encoding and content-length to prevent client decoding failure
ok 19 - handleApiProxy forwards gzipped upstream bodies cleanly without corrupted decoding headers
ok 20 - handleApiProxy preserves upstream redirects without following (redirect: manual)
ok 21 - prepareProxyHeaders suppresses client Authorization header when server API_AUTH_TOKEN is configured
ok 22 - handleApiProxy handles client AbortSignal cleanly
ok 23 - handleApiProxy returns 500 when backend base URL configuration is invalid
1..23
# tests 23
# pass 23
# fail 0
# duration_ms 167.10
```

### 4.2 Next.js Production Build
Executed command: `docker run --rm -v "$PWD/dashboard:/app" -w /app node:20 npm run build`
```
▲ Next.js 16.3.0 (Turbopack)
✓ Running next.config.ts took 68ms
✓ Compiled successfully in 1733ms
  Running TypeScript ...
  Finished TypeScript in 973ms ...
✓ Generating static pages using 8 workers (4/4) in 466ms
Exit code: 0 (Build Succeeded)
```

### 4.3 Frontend Container Image Build
Executed command: `docker build -t business-intelligence-frontend:test dashboard`
- Build time: 20.7s
- Final content size: **73.9 MB**
- Health check: Configured with `wget -q --spider http://127.0.0.1:3000/ || exit 1`
- User: `nextjs` (UID 1001, GID 1001)

### 4.4 Automated Frontend Container Smoke Tests
Executed command: `FRONTEND_IMAGE_TAG="business-intelligence-frontend:test" pytest tests/test_frontend_container_smoke.py -v`
```
tests/test_frontend_container_smoke.py::test_frontend_container_serves_http_root PASSED [ 25%]
tests/test_frontend_container_smoke.py::test_frontend_container_runs_as_non_root PASSED [ 50%]
tests/test_frontend_container_smoke.py::test_frontend_container_excludes_secrets_and_git PASSED [ 75%]
tests/test_frontend_container_smoke.py::test_frontend_container_api_proxy_fails_closed PASSED [100%]
============================== 4 passed in 1.62s ===============================
```

### 4.5 Secret & Layer Audit
Executed command: `docker history business-intelligence-frontend:test --no-trunc && docker inspect business-intelligence-frontend:test --format '{{json .Config.Env}}'`
- Environment variables: `["PATH=...", "NODE_VERSION=20.20.2", "YARN_VERSION=1.22.22", "NODE_ENV=production", "NEXT_TELEMETRY_DISABLED=1", "PORT=3000", "HOSTNAME=0.0.0.0"]`
- Zero build arguments or secrets baked into layers.
- In-container filesystem verified free of `.git`, `.env*`, and `tests/`.

### 4.6 Existing Test Suite Baseline Preservation
1. **Python Offline Test Suite:**
   `DATABASE_URL="postgresql://invalid:invalid@127.0.0.1:59999/nonexistent" pytest -m "not postgres_integration and not docker" -q`
   **Result:** **424 passed, 13 deselected in 6.50s**.
2. **Backend Container Smoke Tests:**
   `DOCKER_IMAGE_TAG="business-intelligence-api:ci" pytest tests/test_container_smoke.py -v`
   **Result:** **8 passed in 1.98s**.

---

## 5. Known Limitations & Future Work

1. **Kubernetes Frontend Manifests (Phase 6H):** Deployment, Service, and Ingress manifests for the frontend pod are not yet created in `deploy/kubernetes/` per Phase 6G constraints.
2. **Playwright/Chromium In-Container Scraper Worker:** In-container Playwright browser scraping remains disabled in the backend container; full headless browser execution will be handled in a dedicated scraper worker image.
3. **Database URL at Build Time:** Next.js pages gracefully fall back to mock data during static page generation when `DATABASE_URL` is omitted. For production deployments with database-backed SSR, `DATABASE_URL` can be optionally supplied at runtime.

---

## 6. Git Working-Tree Status

Per instructions, changes remain uncommitted and unpushed:

```
Changes not staged for commit:
	modified:   .github/workflows/ci.yml
	modified:   dashboard/README.md
	modified:   dashboard/next.config.ts
	modified:   dashboard/package.json

Untracked files:
	AI_MEMORY/PHASE_6G_FRONTEND_CONTAINERIZATION.md
	dashboard/.dockerignore
	dashboard/Dockerfile
	dashboard/tests/containerSmoke.test.mjs
	tests/test_frontend_container_smoke.py
```
