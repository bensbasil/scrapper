# Phase 6K.1: Kubernetes Deployment Architecture Audit

**Project:** Business Opportunity Intelligence Platform  
**Date:** 2026-10-11  
**Role:** Senior DevOps / Platform Architect  
**Scope:** Forensic architecture audit of current container and Kubernetes deployment configurations, definition of frontend Kubernetes requirements, database deployment strategy, and creation of a phased roadmap for complete Kubernetes operationalization.  
**Mode:** AUDIT ONLY (No code, manifest, or workflow modifications made during this phase)

---

## 1. Executive Summary & Audit Verdict

Following the successful migration of all Next.js server-side data reads to FastAPI in Phase 6J.2 and the removal of direct PostgreSQL dependencies from the frontend, the application is architecturally decoupled and ready for unified Kubernetes packaging.

### Key Audit Findings:
1. **Backend Manifests are Production-Grade for Single-Replica Pilot:**
   The backend manifests in `deploy/kubernetes/` enforce strict least-privilege security contexts (non-root `appuser`, drop all capabilities), bounded CPU/memory requests and limits, deterministic rollout strategy (`Recreate` to prevent dual-process scraping and split-brain memory state), and separate liveness/readiness probes.
2. **Frontend Manifests are Currently Absent:**
   Kubernetes manifests exist only for the backend service (`bi-api-service`, `bi-api-deployment`, `bi-api-config`). There are no Kubernetes manifests for the Next.js frontend dashboard (`business-intelligence-frontend`), leaving the user interface reliant on Docker Compose.
3. **Database Boundary is Strictly Enforced:**
   The frontend container is completely decoupled from PostgreSQL: zero `pg` driver dependencies, zero SQL queries, and zero `DATABASE_URL` references. The frontend only requires in-cluster HTTP access to `http://bi-api-service:8000` with the shared `API_AUTH_TOKEN`.
4. **PostgreSQL Strategy Requires Layered Separation:**
   Production workloads should target managed external PostgreSQL (AWS RDS, GCP Cloud SQL) using `DATABASE_URL` in Kubernetes Secrets. However, for local cluster testing (Kind, Minikube) and interview demonstrations, a lightweight in-cluster PostgreSQL deployment should be provided via a Kustomize overlay rather than polluting the base production manifests.
5. **CI/CD Pipeline Has Smoke Test Gaps:**
   GitHub Actions validates backend Docker smoke tests, unit tests, and PostgreSQL integration, but does not execute the containerized frontend smoke test (`test_frontend_container_smoke.py`) and does not validate multi-container integration.

---

## 2. Current Deployment Architecture

### 2.1 Component Overview

```mermaid
graph TD
    subgraph Browser Client
        Browser[User Browser]
    end

    subgraph Kubernetes Cluster (Namespace: default)
        subgraph Frontend Workload (Missing Manifests)
            FE_Pod[Next.js Pod :3000<br/>Standalone Mode<br/>Non-Root: nextjs (1001)]
            FE_Svc[Frontend Service :3000<br/>ClusterIP / NodePort]
        end

        subgraph Backend Workload (deploy/kubernetes/)
            BE_Svc[bi-api-service :8000<br/>ClusterIP]
            BE_Pod[bi-api-deployment :8000<br/>Replicas: 1 (Recreate)<br/>Non-Root: appuser (1000)]
            BE_CM[bi-api-config<br/>ConfigMap]
            BE_Secret[bi-api-secret<br/>Opaque Secret]
        end

        subgraph Database Tier
            InClusterPG[(In-Cluster Postgres :5432<br/>Dev / Demo Overlay)]
        end
    end

    subgraph External Infrastructure
        ExtPG[(Managed Cloud Postgres<br/>AWS RDS / Cloud SQL)]
    end

    Browser -->|HTTP| FE_Svc
    FE_Svc --> FE_Pod
    FE_Pod -->|HTTP + X-API-Key| BE_Svc
    BE_Svc --> BE_Pod
    BE_CM -.->|envFrom| BE_Pod
    BE_Secret -.->|env| BE_Pod
    BE_Secret -.->|API_AUTH_TOKEN| FE_Pod
    BE_Pod -->|DATABASE_URL| InClusterPG
    BE_Pod -.->|Production Option| ExtPG
```

### 2.2 Configuration and Secret Inventory

| Resource | Scope | Sensitivity | Current Source | Consumed By |
| :--- | :--- | :--- | :--- | :--- |
| `API_AUTH_TOKEN` | Shared Secret | **High** | `bi-api-secret` (K8s) / `.env` (Compose) | FastAPI (auth verification) & Next.js (server proxy + SSR client) |
| `DATABASE_URL` | Backend Only | **High** | `bi-api-secret` (K8s) / `.env` (Compose) | FastAPI (`psycopg2` pool); **Strictly omitted from frontend** |
| `GEMINI_API_KEY` | Backend Only | **High** | `bi-api-secret` (K8s) / `.env` (Compose) | FastAPI (LLM capability reasoning, optional with fallback) |
| `API_INTERNAL_URL` | Frontend Only | Low | ConfigMap / Environment (`http://bi-api-service:8000`) | Next.js (`apiProxy.ts` & `apiClient.ts`) |
| `PORT` | Service Port | Low | `bi-api-config` (8000) / Frontend (3000) | Uvicorn / Node.js standalone server |
| `ALLOWED_ORIGINS` | Backend Only | Low | `bi-api-config` | FastAPI CORS Middleware |
| `DB_POOL_*` | Backend Only | Low | `bi-api-config` | `database/db.py` connection pool manager |

---

## 3. Verified Architectural Strengths

1. **Strict Data Boundary Separation (Phase 6J.2):**
   - The frontend container image contains zero database libraries (`pg`, `@types/pg` uninstalled).
   - All server-side data fetching (`/`, `/business/[id]`, `/runs`) routes through `apiClient.ts` to FastAPI.
   - The frontend container runs without `DATABASE_URL`.
2. **Defensive Probe Design:**
   - Backend liveness probe (`/api/health/live`) is unauthenticated and verifies the event loop without querying external databases, eliminating cascading restarts during temporary database hiccups.
   - Backend readiness probe (`/api/health/ready`) verifies database connectivity (`SELECT 1;`) with a 2.0s bounded timeout. If PostgreSQL is offline, the pod is removed from service endpoints without crashing.
   - Backend supports standalone mode gracefully when `DATABASE_URL` is omitted.
3. **Hardened Container Security Contexts:**
   - Both backend (`appuser`, UID 1000) and frontend (`nextjs`, UID 1001) run as unprivileged non-root users.
   - Capabilities are dropped (`drop: ["ALL"]`), and privilege escalation is disallowed (`allowPrivilegeEscalation: false`).
   - `.dockerignore` files in both root and `dashboard/` strictly filter `.git`, `.env*`, tests, and local caches.
4. **Deterministic Single-Replica Rollout Strategy:**
   - Because the backend manages local scraping subprocesses and in-memory log queues, `deployment.yaml` enforces `replicas: 1` and `strategy: { type: Recreate }`.
   - This eliminates split-brain scraping and dual database pool connections during updates.
5. **Decoupled Graceful Shutdown:**
   - Backend specifies `terminationGracePeriodSeconds: 30`.
   - `api_server.py` traps `shutdown` events to send `SIGTERM` (and fallback `SIGKILL`) to child scraper processes before closing the database pool cleanly.

---

## 4. Deployment Gaps & Risks

### 4.1 Gap 1: Missing Frontend Kubernetes Manifests (Severity: HIGH)
- **Finding:** While backend manifests exist in `deploy/kubernetes/`, there are no manifests (`deployment.yaml`, `service.yaml`, `configmap.yaml`) for the Next.js frontend.
- **Impact:** The frontend cannot currently be deployed to a Kubernetes cluster without manual commands.
- **Remediation:** Create `deploy/kubernetes/frontend-deployment.yaml`, `deploy/kubernetes/frontend-service.yaml`, and `deploy/kubernetes/frontend-configmap.yaml`.

### 4.2 Gap 2: In-Cluster vs. Managed Database Ambiguity (Severity: MEDIUM)
- **Finding:** `deploy/kubernetes/` assumes an external PostgreSQL instance (via `DATABASE_URL` in `secret.example.yaml`). However, running the platform in a local test cluster (Minikube or Kind) or an automated demo environment requires an in-cluster database with preloaded schema.
- **Impact:** Developers cannot deploy the complete application to Minikube/Kind using only `kubectl apply -k deploy/kubernetes`.
- **Remediation:** Implement a Kustomize overlay structure: `base/` for core application components, `overlays/local` (or `dev`) with an in-cluster PostgreSQL deployment and schema ConfigMap, and `overlays/prod` for external managed databases.

### 4.3 Gap 3: CI/CD Testing Gaps for Containerized Frontend & Multi-Container Topology (Severity: MEDIUM)
- **Finding:**
  1. `.github/workflows/ci.yml` builds the frontend container (`business-intelligence-frontend:ci`) but runs `npm run test:smoke` (`containerSmoke.test.mjs`), which skips execution when not configured with a Docker socket. The Python smoke test `tests/test_frontend_container_smoke.py` is never run in CI.
  2. CI validates `kubectl kustomize deploy/kubernetes` and `tests/test_kubernetes_manifests.py`, but these only test backend manifests.
  3. No CI job tests the integrated 3-container topology.
- **Impact:** Regressions in the containerized frontend runtime or K8s frontend manifests could slip into main undetected.
- **Remediation:** Wire `test_frontend_container_smoke.py` into the CI Docker testing step and add test coverage for frontend Kubernetes manifests.

### 4.4 Gap 4: Ingress & Public Access Definition (Severity: LOW)
- **Finding:** Currently, services are defined as `ClusterIP`. There is no Ingress or NodePort resource defined for external browser access.
- **Impact:** External users cannot access the dashboard without `kubectl port-forward`.
- **Remediation:** Provide an Ingress resource or configurable NodePort for local/staging environments.

---

## 5. Security & Secret Management Audit

| Risk Item | Severity | Current Status | Recommendation |
| :--- | :--- | :--- | :--- |
| **Committed Secrets** | None (Clean) | `secret.example.yaml` uses placeholder strings (`REPLACE_WITH_STRONG_RANDOM_SECRET`). `.dockerignore` blocks `.env*`. | Maintain strict pre-commit and CI git scanning. |
| **Secret in ConfigMaps** | None (Clean) | `configmap.yaml` contains only non-sensitive configuration keys (`PORT`, `PYTHONUNBUFFERED`, `ALLOWED_ORIGINS`). | Keep tokens strictly in Kubernetes Secrets. |
| **Frontend Secret Boundary** | None (Clean) | Frontend container does not receive `DATABASE_URL`. Token is server-only (`API_AUTH_TOKEN`). | Ensure frontend K8s manifest never references `DATABASE_URL`. |
| **Token Sharing Pattern** | Low | Backend and Frontend must share the same `API_AUTH_TOKEN`. | Both deployments should source `API_AUTH_TOKEN` from the same Secret key (`bi-api-secret` or shared `bi-platform-secret`). |
| **Secret Exemption in Kustomize** | Clean | `kustomization.yaml` intentionally omits `secret.example.yaml` so `kubectl apply -k` does not overwrite live secrets. | Preserve this design; document secret creation step. |

---

## 6. Frontend Kubernetes Requirements Specification

### 6.1 Deployment (`bi-frontend-deployment`)
- **API Version & Kind:** `apps/v1` Deployment
- **Name:** `bi-frontend-deployment`
- **Labels:**
  - `app.kubernetes.io/name: business-intelligence-frontend`
  - `app.kubernetes.io/part-of: business-opportunity-platform`
  - `app.kubernetes.io/component: frontend`
- **Replicas:** 1 (Stateless; can scale to multiple replicas, but 1 is optimal for resource bounding in pilot/demo).
- **Strategy:** `RollingUpdate` (maxSurge: 1, maxUnavailable: 0) — safe because Next.js standalone is stateless.
- **Pod SecurityContext:**
  - `runAsNonRoot: true`
  - `runAsUser: 1001` (matches `nextjs` user in `dashboard/Dockerfile`)
  - `runAsGroup: 1001`
  - `fsGroup: 1001`
  - `seccompProfile: { type: RuntimeDefault }`
- **Container SecurityContext:**
  - `allowPrivilegeEscalation: false`
  - `readOnlyRootFilesystem: false` (Next.js image cache write operations)
  - `capabilities: { drop: ["ALL"] }`
- **Resources:**
  - `requests: { cpu: "100m", memory: "128Mi" }`
  - `limits: { cpu: "500m", memory: "384Mi" }`
- **Environment Variables:**
  - `PORT`: `"3000"` (ConfigMap)
  - `HOSTNAME`: `"0.0.0.0"` (ConfigMap)
  - `NODE_ENV`: `"production"` (ConfigMap)
  - `API_INTERNAL_URL`: `"http://bi-api-service:8000"` (ConfigMap — internal ClusterIP DNS)
  - `API_AUTH_TOKEN`: `valueFrom.secretKeyRef` -> `bi-api-secret.API_AUTH_TOKEN`
  - **DATABASE_URL: STRICTLY OMITTED**
- **Probes:**
  - `startupProbe`: `httpGet` `/`, port: 3000, `initialDelaySeconds: 3`, `periodSeconds: 3`, `failureThreshold: 6`
  - `livenessProbe`: `httpGet` `/`, port: 3000, `periodSeconds: 15`, `timeoutSeconds: 3`, `failureThreshold: 3`
  - `readinessProbe`: `httpGet` `/`, port: 3000, `periodSeconds: 10`, `timeoutSeconds: 3`, `failureThreshold: 2`
  *(Note: Root `/` returns HTTP 200 with empty list even if backend is temporarily disconnected, ensuring frontend pod remains ready while reporting graceful UI status).*

### 6.2 Service (`bi-frontend-service`)
- **API Version & Kind:** `v1` Service
- **Name:** `bi-frontend-service`
- **Type:** `ClusterIP` (base), configurable to `NodePort` or Ingress in overlays.
- **Port:** 3000 (targetPort: 3000, protocol: TCP, name: `http`)
- **Selector:** `app.kubernetes.io/name: business-intelligence-frontend`

---

## 7. PostgreSQL Deployment Decision

### Evaluated Alternatives:
1. **Option A: External / Managed Database Only:**
   - *Pros:* Zero in-cluster storage management, production-grade durability and HA.
   - *Cons:* Breaks local cluster (Kind/Minikube) testing without external cloud setup or port-forwarding.
2. **Option B: In-Cluster StatefulSet / Operator in Base Manifests:**
   - *Pros:* Self-contained in base.
   - *Cons:* Excessive complexity (PV, PVC, StorageClasses, StatefulSet lifecycle) inappropriate for a production base manifest.
3. **Option C: Layered Separation via Kustomize Overlays (Recommended):**
   - **`base/`:** Core stateless application services (`backend` and `frontend`). Consumes `DATABASE_URL` from Secret.
   - **`overlays/local` (or `dev`):** Adds a lightweight in-cluster PostgreSQL deployment + service + ConfigMap mounting `database/schema.sql`, wiring `DATABASE_URL="postgresql://bi_user:bi_password@bi-postgres-service:5432/bi_db"`.
   - **`overlays/prod`:** Omits in-cluster database; relies on external managed PostgreSQL endpoint in `bi-api-secret`.

### Decision:
**Option C.** This cleanly separates production operational concerns from local developer convenience without introducing Helm, operators, or StatefulSet bloat.

---

## 8. CI/CD Gap Analysis

| Workflow Step | Current State | Required State | Priority |
| :--- | :--- | :--- | :--- |
| **Backend Unit & Manifest Tests** | Passes `pytest tests/test_kubernetes_manifests.py` and `kubectl kustomize`. | Retain; expand manifest tests to include frontend. | P2 |
| **Frontend Unit & Smoke Tests** | `npm test` runs 44 tests. `npm run test:smoke` is skipped. | Wire `pytest tests/test_frontend_container_smoke.py` into Docker packaging job. | **P1** |
| **Kustomize Validation** | Runs `kubectl kustomize deploy/kubernetes`. | Update to validate Kustomize build across base and overlays. | P2 |
| **Integrated Multi-Container Validation** | Not executed in CI. | Add lightweight Docker Compose smoke step in CI to verify `frontend -> backend -> postgres` connectivity. | P2 |

---

## 9. Phased Implementation Roadmap

### Phase 6K.2: Frontend Kubernetes Manifest Implementation & Test Suite (Recommended Next Step)
- **Goal:** Implement the audited frontend Kubernetes manifests and automated tests.
- **Deliverables:**
  1. `deploy/kubernetes/frontend-deployment.yaml`
  2. `deploy/kubernetes/frontend-service.yaml`
  3. `deploy/kubernetes/frontend-configmap.yaml`
  4. Update `deploy/kubernetes/kustomization.yaml` to include frontend resources.
  5. Update `tests/test_kubernetes_manifests.py` to validate frontend Deployment, Service, ConfigMap, and secret boundaries (verifying zero `DATABASE_URL`).
  6. Document deployment instructions in `deploy/kubernetes/README.md`.
- **Acceptance Criteria:**
  - `kubectl kustomize deploy/kubernetes` renders both backend and frontend cleanly.
  - Zero `DATABASE_URL` references in frontend manifests.
  - `pytest tests/test_kubernetes_manifests.py` passes 100%.

### Phase 6K.3: Kustomize Overlay Strategy (Local In-Cluster DB vs. External Production)
- **Goal:** Structure manifests into `base/`, `overlays/local` (in-cluster PostgreSQL with schema initialization), and `overlays/prod`.
- **Deliverables:**
  1. `deploy/kubernetes/base/`
  2. `deploy/kubernetes/overlays/local/` (with `postgres-deployment.yaml`, `postgres-service.yaml`, `schema-configmap.yaml`)
  3. `deploy/kubernetes/overlays/prod/`
- **Acceptance Criteria:**
  - Single command `kubectl apply -k deploy/kubernetes/overlays/local` brings up working 3-tier stack on Minikube/Kind.

### Phase 6K.4: CI/CD Pipeline Hardening
- **Goal:** Wire container smoke tests and integrated multi-container verification into `.github/workflows/ci.yml`.
- **Deliverables:**
  1. Run `tests/test_frontend_container_smoke.py` in GitHub Actions.
  2. Add Compose smoke validation step to CI.

---

## 10. Actual Verification Commands & Test Results

The following commands were executed live during this audit to verify current configuration:

1. **Kubernetes Manifest Kustomize Build:**
   ```bash
   kubectl kustomize deploy/kubernetes
   ```
   *Result:* **Success (Exit code 0)**. Output rendered valid ConfigMap (`bi-api-config`), Service (`bi-api-service`), and Deployment (`bi-api-deployment`).

2. **Kubernetes Manifest Automated Test Suite:**
   ```bash
   /tmp/phase6-env/bin/pytest tests/test_kubernetes_manifests.py -v
   ```
   *Result:* **12 passed in 0.06s** (Zero failures).

3. **Frontend Container Smoke Test Suite:**
   ```bash
   /tmp/phase6-env/bin/pytest tests/test_frontend_container_smoke.py -v
   ```
   *Result:* **4 passed in 1.69s** (Verified root HTTP 200, non-root user `nextjs` UID 1001, exclusion of secrets/.git, and 502 proxy fail-closed).

4. **Python Offline Test Suite:**
   ```bash
   /tmp/phase6-env/bin/pytest -m "not postgres_integration and not docker" -q
   ```
   *Result:* **442 passed, 14 deselected in 8.21s**.

5. **Frontend Test Suite:**
   ```bash
   docker run --rm -v "$(pwd)/dashboard":/app -w /app node:20 npm test
   ```
   *Result:* **44 passed, 0 failed, 1 skipped** (152ms).

---

## 11. Explicitly Deferred Complexity

1. **StatefulSet & PersistentVolumeClaims in Base:**
   - StatefulSets, PersistentVolumeClaims, and volume provisioners are intentionally excluded from base manifests. Persistence is managed via external managed databases for production or lightweight overlays for local development.
2. **Kubernetes Operators / Helm Charts:**
   - Operators and Helm charts introduce external tooling dependencies not justified by current project maturity. Kustomize (native to `kubectl`) provides transparent, declarative configuration.
3. **Multi-Replica Backend Autoscaling (HPA):**
   - Deferred until in-memory log queues and scraping subprocesses are externalized (e.g., Redis broker / Celery). Single replica is mathematically required for state consistency.
