# Phase 6F — Deployment Readiness Audit: Python FastAPI + PostgreSQL + Next.js

**Date:** 2026-10-10  
**Auditor:** Senior DevOps & Platform Engineer  
**Scope:** Read-Only Deployment-Readiness Audit across Docker, Kubernetes, Application Runtime, and CI/CD  
**Source Repository:** `bensbasil/scrapper` (Commit `7892b29`)  
**Target Artifact:** `AI_MEMORY/PHASE_6F_DEPLOYMENT_READINESS_AUDIT.md`  

---

## 1. Executive Summary & Readiness Verdict

| Subsystem | Readiness Status | Summary Verdict |
| :--- | :--- | :--- |
| **Backend API Container (`Dockerfile`)** | **PARTIALLY READY** | Non-root execution, hardened build exclusions, and lightweight health checks are properly implemented. Hardcodes port 8000 in `CMD` and lacks Playwright browser binaries for containerized scraping. |
| **Kubernetes Manifests (`deploy/kubernetes/`)** | **READY FOR PILOT (API ONLY)** | Compiles cleanly via Kustomize; single-replica `Recreate` strategy safely aligns with in-memory state; non-root security contexts and calibrated probes are verified. Only deploys the backend API. |
| **Application Runtime (`api_server.py`)** | **PRODUCTION READY** | Liveness probe is fast and fully decoupled from DB/LLM; readiness probe distinguishes standalone vs. connected vs. degraded mode; constant-time API token auth and bounded connection pooling fail closed with zero credential leaks. |
| **Frontend Dashboard (`dashboard/`)** | **NOT DEPLOYMENT READY** | Next.js build succeeds, but client-side API requests lack `X-API-Key` headers (failing with 401); proxy rewrite hardcodes `127.0.0.1:8000`; SSE log streaming route is missing; no Dockerfile or Kubernetes manifests exist for the frontend. |
| **CI/CD Pipeline (`ci.yml`)** | **VERIFIED (SCOPED)** | All 4 jobs (`test-offline`, `test-postgres-integration`, `docker-build`, `frontend-build`) validate their scoped gates, but CI does not test frontend-to-backend integration or authenticated browser traffic. |

**Overall Verdict:** The **FastAPI backend API** is structurally hardened and ready for a single-replica pilot deployment. The **Next.js frontend** cannot function against the authenticated backend in a distributed or containerized deployment without remediation of client-side authentication headers, configurable API proxying, and container packaging.

---

## 2. Docker Audit Findings

### 2.1 Non-Root Execution
- **File:** [`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile#L20-L37)
- **Implementation:**
  ```dockerfile
  RUN groupadd --gid 1000 appgroup && \
      useradd --uid 1000 --gid appgroup --create-home --shell /bin/bash appuser
  ...
  USER appuser
  ```
- **Verification:** Verified by [`tests/test_container_smoke.py::test_container_runs_as_non_root_user`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py#L107-L116) (`uid=1000(appuser)` and `gid=1000(appgroup)`).
- **Assessment:** **PASS**. Adheres to container least-privilege standards.

### 2.2 Exposed Port & Startup Command
- **File:** [`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile#L13, #L39, #L48)
- **Implementation:**
  ```dockerfile
  ENV PORT=8000
  EXPOSE 8000
  CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
- **Finding [P2-3]:** In `Dockerfile`, `ENV PORT=8000` is declared, but `CMD` uses exec form with a literal string `"8000"`. Exec form does not invoke a shell and therefore does not perform environment variable expansion (`$PORT`).
- **Impact:** Cloud PaaS environments (e.g., Google Cloud Run, AWS ECS, Heroku) that inject dynamic `$PORT` values cannot reconfigure the port via environment variable alone without overriding the command.
- **Recommendation:** Change `CMD` to shell wrapper or utilize `sh -c 'exec uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8000}'` or configure uvicorn to consume `PORT` from environment via custom startup script.

### 2.3 Required Runtime Dependencies & Headless Browser Gap
- **File:** [`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile#L16-L28), [`scraper/connectors/public_web/google_maps.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/connectors/public_web/google_maps.py#L9, #L174)
- **Implementation:**
  `Dockerfile` installs `curl` and Python dependencies from `requirements.lock` (`playwright==1.42.0`). It does **not** execute `playwright install chromium` or install Chromium operating system dependencies.
- **Finding [P1-1]:**
  The Python API server exposes `POST /api/scrape` and `POST /api/recrawl`, which invoke `pipeline_runner.py`. In turn, `pipeline_runner.py` executes `GoogleMapsScraper`, which invokes:
  ```python
  with sync_playwright() as p:
      browser = p.chromium.launch(headless=self.headless)
  ```
- **Impact:** If an operator triggers scraping inside this container, Playwright will fail with `Executable doesn't exist at /home/appuser/.cache/ms-playwright/chromium-...`.
- **Recommendation:** For the API container, maintain it as an API/reasoning server, or separate scraping workloads into an asynchronous worker container image built on `mcr.microsoft.com/playwright/python:v1.42.0-jammy` or including `playwright install --with-deps chromium`.

### 2.4 Environment Variables & Secrets Handling
- **File:** [`.dockerignore`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.dockerignore#L1-L26), [`tests/test_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py#L120-L135)
- **Implementation:** `.dockerignore` excludes `.env*`, `.git`, `.venv`, `__pycache__`, tests, and database dump files.
- **Verification:** Verified by `test_container_excludes_secrets_and_git`. Zero credentials or secret defaults are baked into image layers.
- **Assessment:** **PASS**.

### 2.5 Graceful Shutdown Handling
- **File:** [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L474-L508), [`Dockerfile`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile#L48)
- **Implementation:**
  `CMD ["uvicorn", ...]` executes uvicorn as PID 1, receiving `SIGTERM` directly. The `@app.on_event("shutdown")` lifecycle handler terminates active scraper subprocesses (`terminate()`, 1s grace period, followed by `kill()`) and calls `db_manager.close()` to drain the pool.
- **Verification:** Verified by `test_container_readiness_with_unreachable_database` testing clean exit on `docker stop -t 5`.
- **Assessment:** **PASS**.

---

## 3. Kubernetes Audit Findings

### 3.1 Deployment Image & Pull Behavior
- **File:** [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L51-L52)
- **Implementation:**
  ```yaml
  image: business-intelligence-api:latest
  imagePullPolicy: IfNotPresent
  ```
- **Finding [P2-1]:** The manifest specifies floating tag `:latest` with `imagePullPolicy: IfNotPresent`.
- **Impact:** In multi-node Kubernetes clusters, if an image tag `:latest` is already cached on a node, `IfNotPresent` will skip pulling updated builds during rollouts. This is suitable for local single-node development (Docker Desktop / Kind) but hazardous in production.
- **Recommendation:** Use immutable image digest or semver tags (e.g. `:v1.0.0` or git commit SHA) in production, or set `imagePullPolicy: Always` when using floating tags across multiple nodes.

### 3.2 Container Port & Service Consistency
- **File:** [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L54-L57), [`deploy/kubernetes/service.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/service.yaml#L11-L15)
- **Implementation:**
  - Deployment defines named port `http` on `containerPort: 8000`.
  - Service exposes port `8000` with `targetPort: http`.
  - Selector `app.kubernetes.io/name: business-intelligence-api` matches Deployment metadata and template labels.
- **Verification:** Verified by [`tests/test_kubernetes_manifests.py::test_service_spec_and_port_alignment`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_kubernetes_manifests.py#L192-L208).
- **Assessment:** **PASS**.

### 3.3 Probe Definitions & Behavioral Contracts
- **File:** [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L93-L116)
- **Implementation:**
  - `startupProbe`: `path: /api/health/live`, `port: http`, `failureThreshold: 6`, `periodSeconds: 5`, `initialDelaySeconds: 2` (up to 32s budget for Python module imports).
  - `livenessProbe`: `path: /api/health/live`, `port: http`, `failureThreshold: 3`, `periodSeconds: 10`, `timeoutSeconds: 3`.
  - `readinessProbe`: `path: /api/health/ready`, `port: http`, `failureThreshold: 2`, `periodSeconds: 10`, `timeoutSeconds: 3`.
- **Assessment:** **PASS**. Probe configuration correctly decouples process liveness from external dependencies while readiness accurately gates traffic on PostgreSQL connectivity.

### 3.4 Resource Requests & Limits
- **File:** [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L64-L70)
- **Implementation:**
  - Requests: `cpu: 100m`, `memory: 256Mi`
  - Limits: `cpu: 1000m`, `memory: 512Mi`
- **Finding [P2-2]:** Limits are appropriately sized for the Python FastAPI server and deterministic agent evaluation. However, if browser scraping is initiated inside this pod, a single Chromium instance consumes 500Mi–1GiB+, risking pod eviction via Linux OOMKilled.
- **Recommendation:** Maintain current limits for the API server; disallow in-pod Playwright scraping or offload scraper jobs to external workers.

### 3.5 ConfigMap & Secret References
- **File:** [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L71-L91), [`deploy/kubernetes/secret.example.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/secret.example.yaml)
- **Implementation:**
  - `envFrom` references `bi-api-config`.
  - `API_AUTH_TOKEN` is mandatory from `bi-api-secret`.
  - `DATABASE_URL` and `GEMINI_API_KEY` are marked `optional: true`.
  - `secret.example.yaml` is excluded from `kustomization.yaml` to avoid overwriting live secrets with placeholders.
- **Assessment:** **PASS**.

### 3.6 Persistent Storage & Single-Replica Architecture
- **File:** [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L10-L30)
- **Implementation:**
  - `replicas: 1`
  - `strategy.type: Recreate`
  - Zero PVCs / StatefulSets.
- **Architectural Verification:** Verified by regression tests in [`tests/test_kubernetes_manifests.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_kubernetes_manifests.py#L91-L106, #L224-L250). The application stores agent task responses (`agent_task_store`), log queues, and active scraper handles in host process memory. Multiple replicas cause 404s on task lookups and split-brain scraper execution. `Recreate` ensures old pods terminate completely before replacement pods launch, accepting ~5–15s of downtime during updates.
- **Assessment:** **PASS (FOR PILOT)**. Correctly documented architectural trade-off.

### 3.7 Kustomize Compilation
- **File:** [`deploy/kubernetes/kustomization.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/kustomization.yaml)
- **Verification:** `kubectl kustomize deploy/kubernetes` compiles with exit code 0 and emits clean, valid Kubernetes resources.
- **Assessment:** **PASS**.

---

## 4. Application Runtime Audit Findings

### 4.1 Health Endpoints Contract & Isolation
- **File:** [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L359-L457)
- **Implementation:**
  - `/api/health/live`: Computes `uptime_seconds` in memory. Zero external calls, zero DB queries. Unauthenticated.
  - `/api/health/ready`:
    - If `DATABASE_URL` is absent: Returns HTTP 200 (`mode: standalone`, `database: unconfigured`).
    - If `DATABASE_URL` is present and reachable: Checks `SELECT 1;` with 2.0s timeout and returns HTTP 200 (`mode: connected`, `database: connected`).
    - If `DATABASE_URL` is unreachable: Catches exception, sets HTTP 503 (`mode: connected`, `database: unavailable`), returns generic error message.
  - Information Disclosure Prevention: Verified by tests. Password, port, host, and database name are never returned in 503 responses.
- **Assessment:** **PASS**.

### 4.2 Standalone Mode & Optional Credentials
- **File:** [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L427-L439), [`ai/config.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/ai/config.py#L65-L120)
- **Implementation:**
  - When `GEMINI_API_KEY` is missing: `LLMConfig` defaults to `provider="none"`. Agents and outreach generators fall back to deterministic scoring and rule-based outreach templates.
  - Readiness probe reports `components.llm: {"status": "fallback", "provider": "deterministic"}` without failing readiness.
- **Assessment:** **PASS**.

### 4.3 Missing Configuration & Error Handling
- **File:** [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L57-L82), [`database/db.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/db.py#L51-L94)
- **Implementation:**
  - Missing `API_AUTH_TOKEN`: `verify_api_key` immediately raises HTTP 401 with explicit error: `"Authentication failed: server API authentication token is not configured."`
  - Missing `DATABASE_URL`: `resolve_database_url` raises `DatabaseConfigurationError`. Endpoints needing DB return sanitized 500 without leaking connection credentials.
- **Assessment:** **PASS**.

### 4.4 Database Failures & Connection Pool Bounding
- **File:** [`database/db.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/db.py#L100-L250)
- **Implementation:**
  - `BoundedConnectionPool` wraps `ThreadedConnectionPool` with a condition lock. If the pool is exhausted, requests wait up to `DB_POOL_TIMEOUT` (default 10.0s) before raising `DatabasePoolTimeoutError`.
  - Connections checked out via `get_connection()` context manager always execute `conn.rollback()` on error and `putconn(conn)` in `finally:`, preventing leaked connections.
- **Assessment:** **PASS**.

---

## 5. Frontend & CI/CD Audit Findings

### 5.1 Frontend Client-Side API Authentication Mismatch
- **File:** [`dashboard/src/components/BusinessDashboard.tsx`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/src/components/BusinessDashboard.tsx#L88, #L133, #L202, #L229, #L246), [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L47-L84, #L514, #L655, #L687)
- **Evidence:**
  In `BusinessDashboard.tsx`:
  ```typescript
  // Line 88:
  const res = await fetch("/api/businesses");
  
  // Line 202:
  const res = await fetch("/api/scrape", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(...)
  });
  
  // Line 229:
  const res = await fetch("/api/stop", { method: "POST" });
  ```
  In `api_server.py`:
  ```python
  @app.get("/api/businesses", dependencies=[Depends(verify_api_key)])
  @app.post("/api/scrape", dependencies=[Depends(verify_api_key)])
  @app.post("/api/stop", dependencies=[Depends(verify_api_key)])
  ```
- **Finding [P0-1]:** The FastAPI backend strictly requires authentication on `/api/businesses`, `/api/scrape`, `/api/stop`, etc. via `verify_api_key`. The Next.js frontend sends **no `X-API-Key` or `Authorization` headers**.
- **Impact:** In any deployed environment where `API_AUTH_TOKEN` is configured, all browser fetches to the API fail with `HTTP 401 Unauthorized`. The UI cannot fetch live prospects, cannot trigger scraping, and cannot terminate scraping processes.
- **Recommendation:** Implement client-side API key configuration or inject the server-side API auth token through Next.js server-side route handlers / middleware proxying requests to the backend.

### 5.2 Next.js Proxy Rewrite Hardcodes Localhost
- **File:** [`dashboard/next.config.ts`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/next.config.ts#L4-L12)
- **Evidence:**
  ```typescript
  async rewrites() {
    return [
      {
        source: "/api/:path((?!logs$).*)",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  }
  ```
- **Finding [P0-2]:** The Next.js rewrite hardcodes `http://127.0.0.1:8000`.
- **Impact:** In Kubernetes or containerized environments, the Next.js frontend pod cannot communicate with the backend API service via `127.0.0.1:8000` because pods have distinct network namespaces. In Kubernetes, the target service is `http://bi-api-service:8000`. Without an environment variable (e.g. `API_INTERNAL_URL`), the frontend proxy breaks completely upon deployment.
- **Recommendation:** Update `next.config.ts` to read `process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"`.

### 5.3 Missing SSE Log Streaming Route Handler
- **File:** [`dashboard/next.config.ts`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/next.config.ts#L7-L9), [`dashboard/src/components/BusinessDashboard.tsx`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/src/components/BusinessDashboard.tsx#L165)
- **Evidence:**
  `next.config.ts` uses regex `source: "/api/:path((?!logs$).*)"` to intentionally exclude `/api/logs`, with comment: `// Exclude /api/logs — handled natively by src/app/api/logs/route.ts (SSE streaming)`.
  However, directory `dashboard/src/app/api/logs/` does not exist in the filesystem.
- **Finding [P1-3]:** In `BusinessDashboard.tsx`, `const eventSource = new EventSource("/api/logs");` is invoked. Because it is excluded from Next.js rewrites and has no route handler, the request returns HTTP 404.
- **Impact:** Real-time log streaming in the dashboard UI does not function.
- **Recommendation:** Either implement `dashboard/src/app/api/logs/route.ts` as an SSE streaming proxy with authentication, or remove the negative lookahead from `next.config.ts` so `/api/logs` is forwarded to FastAPI.

### 5.4 Missing Frontend Packaging & Manifests
- **File:** [`dashboard/`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/), [`deploy/kubernetes/`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/)
- **Finding [P1-2]:**
  - No `Dockerfile` exists for the Next.js dashboard.
  - No Kubernetes manifests exist for deploying the frontend application, creating an ingress, or managing frontend configuration.
- **Impact:** Only the Python API container can be built and deployed via the existing Kubernetes manifests. The Next.js dashboard must currently be run manually on the host.
- **Recommendation:** Create a multi-stage `dashboard/Dockerfile` (Node 20 Alpine) and add `frontend-deployment.yaml`, `frontend-service.yaml`, and an Ingress manifest to `deploy/kubernetes/`.

### 5.5 CI Verification Gaps
- **File:** [`.github/workflows/ci.yml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml)
- **Findings [P3-2]:**
  - `ci.yml` runs `npm run build` in isolation without starting the backend or checking whether API calls succeed.
  - `ci.yml` runs Docker smoke tests against `/api/health/live`, `/api/health/ready`, and `/api/status`, but does not attempt to trigger `POST /api/scrape` in the container (which would uncover the missing Playwright Chromium binaries).
  - `ci.yml` validates `kubectl kustomize deploy/kubernetes` syntax, but does not deploy to a cluster.

---

## 6. Comprehensive Prioritized Findings Matrix

| ID | Priority | Category | File Path & Location | Summary of Finding | Recommended Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P0-1** | **P0** | Security / Auth | [`dashboard/src/components/BusinessDashboard.tsx:88-246`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/src/components/BusinessDashboard.tsx#L88) | Dashboard UI `fetch` calls lack `X-API-Key` authentication headers required by `api_server.py`. | Add API token header to frontend requests or proxy through an authenticated server route. |
| **P0-2** | **P0** | Networking | [`dashboard/next.config.ts:8-10`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/next.config.ts#L8-L10) | Next.js API rewrite hardcodes `127.0.0.1:8000`, breaking routing in containerized/K8s networks. | Use environment variable `process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"`. |
| **P1-1** | **P1** | Dependencies | [`Dockerfile:16-28`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile#L16-L28) | Container image lacks Playwright Chromium binaries and OS libraries; scraper subprocess will crash. | Separate scraping workloads into worker image or add `playwright install --with-deps chromium`. |
| **P1-2** | **P1** | Packaging | [`dashboard/`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/), [`deploy/kubernetes/`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/) | Next.js dashboard lacks a Dockerfile and Kubernetes manifests for cluster deployment. | Create frontend Dockerfile and add frontend Kubernetes Deployment, Service, and Ingress. |
| **P1-3** | **P1** | Runtime / SSE | [`dashboard/next.config.ts:8`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/next.config.ts#L8) | `/api/logs` excluded from rewrites, but referenced `src/app/api/logs/route.ts` does not exist. | Create `src/app/api/logs/route.ts` or allow rewrite rule to proxy `/api/logs`. |
| **P2-1** | **P2** | Kubernetes | [`deploy/kubernetes/deployment.yaml:51-52`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L51-L52) | Deployment uses `:latest` tag with `imagePullPolicy: IfNotPresent`. | Use immutable semver or git SHA tags in production. |
| **P2-2** | **P2** | Resources | [`deploy/kubernetes/deployment.yaml:70`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml#L70) | Memory limit 512Mi is too tight for headless browser scraping. | Prevent in-pod scraping or increase memory limits for dedicated scraper workers. |
| **P2-3** | **P2** | Docker | [`Dockerfile:48`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/Dockerfile#L48) | `CMD` hardcodes port `8000` in exec form, ignoring dynamic `$PORT` environment variable. | Use shell form or entrypoint script to expand `${PORT:-8000}`. |
| **P3-1** | **P3** | Documentation | [`deploy/kubernetes/README.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/README.md) | Guide details backend API deployment only; omits frontend dashboard deployment. | Document frontend architecture, environment variables, and deployment options. |
| **P3-2** | **P3** | CI/CD | [`.github/workflows/ci.yml:125-147`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml#L125-L147) | CI builds frontend statically but does not test frontend-to-backend proxying or auth. | Add integration test verifying frontend API client against authenticated backend. |
