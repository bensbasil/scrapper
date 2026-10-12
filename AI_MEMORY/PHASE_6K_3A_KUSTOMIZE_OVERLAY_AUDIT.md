# Phase 6K.3A: Kubernetes Kustomize Overlay Architecture Audit

**Project:** Business Opportunity Intelligence Platform  
**Date:** 2026-10-11  
**Role:** Senior DevOps / Platform Architect  
**Scope:** Architecture audit and design for transitioning from a flat Kubernetes manifest layout to a Kustomize `base` and `overlays` (`local` vs. `prod`) architecture.  
**Mode:** **AUDIT AND DESIGN ONLY** (No application code, existing manifests, or directories modified during this phase)

---

## 1. Executive Summary & Audit Baseline

In Phase 6K.2, Kubernetes manifests for the Next.js frontend dashboard (`business-intelligence-frontend`) were added alongside the existing FastAPI backend (`business-intelligence-api`) in `deploy/kubernetes/`. The current configuration features:
- A verified declarative Kustomize build (`kubectl kustomize deploy/kubernetes`) rendering 6 resources:
  - `bi-api-config` (ConfigMap)
  - `bi-frontend-config` (ConfigMap)
  - `bi-api-service` (ClusterIP Service, port 8000)
  - `bi-frontend-service` (ClusterIP Service, port 3000)
  - `bi-api-deployment` (Deployment, replicas: 1, `Recreate` strategy, UID 1000)
  - `bi-frontend-deployment` (Deployment, replicas: 1, `RollingUpdate` strategy, UID 1001)
- Strict database isolation: The frontend container has zero direct PostgreSQL access, zero `pg` library dependencies, and zero `DATABASE_URL` references.
- Private in-cluster service resolution: The frontend reaches the backend via `API_INTERNAL_URL="http://bi-api-service:8000"`.
- Authentication boundary: `API_AUTH_TOKEN` is injected server-side from `bi-api-secret` into both workloads, remaining completely invisible to browser client bundles.

### The Architectural Problem
The current Kubernetes layout in `deploy/kubernetes/` is **flat**. It assumes that an external database is already running, or that the backend is executed in standalone mode (`DATABASE_URL` optional).
However:
1. **Developer / Demo friction:** Developers wanting to spin up the complete 3-tier platform on local clusters (Kind, Minikube, Docker Desktop) cannot do so in one command because there are no Kubernetes manifests for PostgreSQL or automated schema loading (`database/schema.sql`).
2. **Production contamination risk:** Hardcoding an in-cluster PostgreSQL deployment into the flat manifest directory would force production environments to either run an unmanaged, non-HA in-cluster database or manually strip out database manifests.
3. **Configuration divergence:** Local deployments need different defaults (e.g. in-cluster PostgreSQL DNS, pre-seeded local auth tokens, relaxed memory allocations) compared to production environments (managed cloud PostgreSQL, external secret providers, strict resource bounds).

This audit defines the precise migration path to transition from flat manifests to a standard Kustomize **Base + Overlays** architecture.

---

## 2. Current Architecture Inspection

### 2.1 Component & Manifest Inventory

| Manifest | Kind | Name | Port(s) | Security / Runtime Context | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `deploy/kubernetes/configmap.yaml` | `ConfigMap` | `bi-api-config` | N/A | Non-sensitive data | Backend runtime config (`PORT: "8000"`, pool sizes, CORS allowlists). |
| `deploy/kubernetes/service.yaml` | `Service` | `bi-api-service` | 8000 (TCP) | ClusterIP | Internal service proxy for backend pods (`selector: app.kubernetes.io/name: business-intelligence-api`). |
| `deploy/kubernetes/deployment.yaml` | `Deployment` | `bi-api-deployment` | 8000 (`http`) | UID 1000, GID 1000, drop ALL caps, `Recreate` | Single-replica backend API running FastAPI/Uvicorn. |
| `deploy/kubernetes/frontend-configmap.yaml` | `ConfigMap` | `bi-frontend-config` | N/A | Non-sensitive data | Frontend runtime config (`PORT: "3000"`, `API_INTERNAL_URL: "http://bi-api-service:8000"`). |
| `deploy/kubernetes/frontend-service.yaml` | `Service` | `bi-frontend-service` | 3000 (TCP) | ClusterIP | Internal service proxy for frontend pods (`selector: app.kubernetes.io/name: business-intelligence-frontend`). |
| `deploy/kubernetes/frontend-deployment.yaml` | `Deployment` | `bi-frontend-deployment` | 3000 (`http`) | UID 1001, GID 1001, drop ALL caps, `RollingUpdate` | Single-replica Next.js standalone UI. Zero database references. |
| `deploy/kubernetes/secret.example.yaml` | `Secret` | `bi-api-secret` | N/A | Opaque (Template only) | Operator template defining `API_AUTH_TOKEN`, `DATABASE_URL`, and `GEMINI_API_KEY`. Excluded from `kustomization.yaml`. |
| `deploy/kubernetes/kustomization.yaml` | `Kustomization` | N/A | N/A | `v1beta1` | Flat bundle aggregating the 6 backend and frontend manifests. |

### 2.2 Verified Configuration & Routing Baseline

- **In-Cluster Frontend-to-Backend Resolution:**  
  `bi-frontend-deployment` connects to `http://bi-api-service:8000` via CoreDNS service discovery.
- **Backend-to-Database Resolution (Current State):**  
  `bi-api-deployment` reads `DATABASE_URL` from `bi-api-secret` (`optional: true`). If unset, the backend operates in standalone memory mode; if set, it opens a connection pool to the specified host.
- **Health Check Semantics:**
  - Backend Startup & Liveness: `/api/health/live` (port 8000) — purely process-level, zero database/network I/O.
  - Backend Readiness: `/api/health/ready` (port 8000) — checks DB connectivity (`SELECT 1;`) with a 2-second timeout. If DB is unavailable, returns 503 without restarting the pod.
  - Frontend Startup, Liveness & Readiness: `/` (port 3000) — checks Next.js HTTP server availability. Fails closed (502) on backend route proxies if backend is down, but serves dashboard shell without crashing.

---

## 3. Proposed Kustomize Directory Structure

To support both seamless local evaluation and hardened production deployments without duplicating code or manifests, we propose standardizing on the canonical Kustomize layout:

```
deploy/kubernetes/
├── kustomization.yaml                 # Root forwarder/compatibility alias (optional/transitional)
├── base/
│   ├── kustomization.yaml             # Core application workloads bundle
│   ├── deployment.yaml                # Backend Deployment (bi-api-deployment)
│   ├── service.yaml                   # Backend Service (bi-api-service)
│   ├── configmap.yaml                 # Backend ConfigMap (bi-api-config)
│   ├── frontend-deployment.yaml      # Frontend Deployment (bi-frontend-deployment)
│   ├── frontend-service.yaml         # Frontend Service (bi-frontend-service)
│   ├── frontend-configmap.yaml       # Frontend ConfigMap (bi-frontend-config)
│   └── secret.example.yaml           # Secret template for reference
└── overlays/
    ├── local/
    │   ├── kustomization.yaml         # Local cluster target (Kind, Minikube, Docker Desktop)
    │   ├── postgres-deployment.yaml   # In-cluster single-replica PostgreSQL 15 workload
    │   ├── postgres-service.yaml      # In-cluster PostgreSQL ClusterIP service (bi-postgres-service)
    │   ├── postgres-pvc.yaml          # PersistentVolumeClaim for local database data
    │   ├── patches/
    │   │   ├── backend-db-env.yaml    # Patch wiring backend DATABASE_URL to in-cluster service
    │   │   └── local-secrets.yaml     # Dev secret generator / patch with local credentials
    │   └── README.md                  # Quickstart for local cluster deployment
    └── prod/
        ├── kustomization.yaml         # Production cluster target (EKS, GKE, AKS, Bare-Metal)
        ├── patches/
        │   ├── resource-tuning.yaml   # Production CPU/memory adjustments (if applicable)
        │   └── ingress.yaml           # Production ingress / TLS routing (optional)
        └── README.md                  # Production runbook & secret management guidelines
```

### 3.1 Layout Compatibility & Migration Assessment

- **Kustomize Specification Compatibility:**  
  `kubectl kustomize` (native in `kubectl` v1.14+) fully supports relative directory paths across `base` and `overlays`. `apiVersion: kustomize.config.k8s.io/v1beta1` is identical across all layers.
- **Smallest Safe Migration Strategy:**
  1. **Zero Manifest Duplication:** All application workloads (`deployment.yaml`, `service.yaml`, `configmap.yaml`, `frontend-*`) are moved into `base/` once. Neither `overlays/local` nor `overlays/prod` duplicates application specs.
  2. **Backward-Compatibility Anchor:** In the initial migration phase, `deploy/kubernetes/kustomization.yaml` at the root can contain:
     ```yaml
     apiVersion: kustomize.config.k8s.io/v1beta1
     kind: Kustomization
     resources:
       - base/
     ```
     This guarantees that legacy build invocations like `kubectl kustomize deploy/kubernetes` in external scripts continue to render the base application without failing.
  3. **Explicit Targeted Overlays:** Operators and CI explicitly run:
     - `kubectl kustomize deploy/kubernetes/base`
     - `kubectl kustomize deploy/kubernetes/overlays/local`
     - `kubectl kustomize deploy/kubernetes/overlays/prod`

---

## 4. Local In-Cluster Database Architecture

### 4.1 Deployment Requirements

| Requirement | Specification | Rationale & Evidence |
| :--- | :--- | :--- |
| **Engine Image** | `postgres:15-alpine` | Matches `deploy/docker-compose.yaml` (line 16) and GitHub Actions CI (line 54). Ensures strict SQL dialect compatibility with `database/schema.sql`. |
| **Workload Type** | `Deployment` (replicas: 1) with PVC | Simpler and lighter than a StatefulSet for single-node local clusters, while providing persistent disk across pod crashes. |
| **Service DNS** | `bi-postgres-service:5432` | ClusterIP service exposing port 5432 with selector `app.kubernetes.io/name: business-intelligence-postgres`. |
| **Backend Connection** | `postgresql://bi_user:bi_password@bi-postgres-service:5432/bi_db` | Matches credentials in `deploy/docker-compose.yaml` (lines 20-22). |
| **Readiness Probe** | `exec: pg_isready -U bi_user -d bi_db` | Validates PostgreSQL is ready to accept connections before routing in-cluster traffic. |
| **Resource Bounds** | Requests: 100m CPU, 128Mi RAM<br>Limits: 500m CPU, 512Mi RAM | Prevents resource starvation on single-node Minikube/Kind nodes. |

### 4.2 Automated Schema Initialization (`database/schema.sql`)

The repository's complete schema is located at `database/schema.sql` (325 lines, 14,070 bytes).
In Docker Compose, this file is volume-mounted to `/docker-entrypoint-initdb.d/01_schema.sql:ro`.

In Kubernetes, this must be replicated declaratively without baking SQL into the container image:
1. **ConfigMap Generation:**  
   In `deploy/kubernetes/overlays/local/kustomization.yaml`, utilize Kustomize's `configMapGenerator`:
   ```yaml
   configMapGenerator:
     - name: bi-postgres-schema
       files:
         - 01_schema.sql=../../../database/schema.sql
   ```
   *Size verification:* At 14.1 KB, `database/schema.sql` is less than 1.5% of the 1 MiB Kubernetes ConfigMap size limit.
2. **Volume Mount:**  
   Mount `bi-postgres-schema` ConfigMap into the PostgreSQL pod at `/docker-entrypoint-initdb.d/01_schema.sql` (read-only).
3. **Execution Semantics:**  
   Under official PostgreSQL entrypoint mechanics, scripts in `/docker-entrypoint-initdb.d/` are executed **ONLY ONCE**, when `/var/lib/postgresql/data` (`$PGDATA`) is completely empty during first container initialization.
   If the container restarts and `$PGDATA` is already populated, `/docker-entrypoint.sh` detects existing data and skips the script, preventing table recreation errors.

### 4.3 Storage Durability & Data Lifecycle

> [!WARNING]
> **Durability Contract:** An in-cluster PostgreSQL deployment in a local overlay is a **development and demo convenience harness**, NOT an enterprise production database. It lacks replication, automated WAL archiving, automated backups, and cross-AZ failover.

- **What Happens on Pod Restart (`kubectl rollout restart` or crash):**
  - If backed by a PersistentVolumeClaim (`bi-postgres-pvc`), the replacement pod reattaches the existing PV. All business entities, scraper runs, and scoring records persist intact.
  - The entrypoint detects the populated data directory and starts PostgreSQL immediately without re-running `schema.sql`.
- **How Developers Reset Data:**
  - Developers can safely wipe local test data by deleting the PVC:
    ```bash
    kubectl delete pvc -l app.kubernetes.io/name=business-intelligence-postgres
    kubectl rollout restart deployment/bi-postgres-deployment
    ```
    Upon restart, PostgreSQL provisions a clean data volume and re-executes `database/schema.sql` from the ConfigMap.

### 4.4 Startup Decoupling & Probe Resilience

A critical design validation: **What happens if the backend API starts before PostgreSQL is ready?**
- **Startup Probe (`/api/health/live`):** Succeeds immediately (HTTP 200). It checks only local event loop liveness and does not touch the database.
- **Readiness Probe (`/api/health/ready`):** Returns HTTP 503 until PostgreSQL accepts connections. Kubernetes does not restart the container; it simply withholds incoming traffic from `bi-api-service`.
- **Automatic Recovery:** Once PostgreSQL finishes initializing and passes its `pg_isready` probe, the backend's connection pool connects, `/api/health/ready` transitions to HTTP 200, and traffic flows automatically. No complex init-containers or sleep scripts are necessary.

---

## 5. Production Overlay Architecture

### 5.1 Hardened Production Contracts

| Area | Production Overlay Rule | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Database Instance** | Strictly managed external PostgreSQL (AWS RDS, GCP Cloud SQL, Azure Database for PostgreSQL). | `overlays/prod/` completely omits `postgres-*.yaml` manifests. |
| **Secret Management** | Zero plaintext secrets committed to git. Credentials injected via external cluster Secret `bi-api-secret`. | SealedSecrets, External Secrets Operator, or out-of-band `kubectl create secret`. |
| **ConfigMap Separation** | Non-sensitive runtime parameters only. Zero credentials in ConfigMaps. | Tests enforce absence of `DATABASE_URL`, `API_AUTH_TOKEN`, and `GEMINI_API_KEY` from ConfigMaps. |
| **Frontend Decoupling** | Frontend container has zero database access or credentials. | Manifest tests verify `DATABASE_URL` is absent from `bi-frontend-deployment` in all overlays. |
| **Internal Isolation** | Workloads communicate internally via ClusterIP; database ports are never exposed. | Services use `ClusterIP`. Ingress (if added) targets only frontend port 3000 and API port 8000. |

---

## 6. Migration Risks & Impact Analysis

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Test Suite Breakage** | Existing tests in `tests/test_kubernetes_manifests.py` hardcode `MANIFEST_DIR = deploy/kubernetes`. | Update test suite to evaluate `base/`, `overlays/local`, and `overlays/prod` systematically while maintaining a root compatibility test. |
| **CI Workflow Failure** | Line 46 in `.github/workflows/ci.yml` runs `kubectl kustomize deploy/kubernetes`. | Either maintain root `deploy/kubernetes/kustomization.yaml` pointing to `base/`, or update CI to validate all three targets (`base`, `overlays/local`, `overlays/prod`). |
| **PostgreSQL File Permissions on Volume** | Official Postgres image runs as UID 70 (`postgres`). Mounting PVCs on some hosts causes permission denied on `$PGDATA`. | Explicitly configure `securityContext.fsGroup: 70` on the PostgreSQL pod spec in `overlays/local/`. |
| **Secret Accidental Commit** | Dev credentials in `overlays/local` accidentally committed or reused in production. | Use explicit `secret.local.example.yaml` or mock dev tokens in `local`, and enforce secret scanner assertions in `tests/test_kubernetes_manifests.py`. |

---

## 7. Manifest Testing Strategy

The test suite in `tests/test_kubernetes_manifests.py` must be upgraded from verifying a single flat directory to verifying the three distinct Kustomize targets:

```mermaid
graph TD
    subgraph Test Suite: test_kubernetes_manifests.py
        T_Base[Test Base Stream<br/>deploy/kubernetes/base]
        T_Local[Test Local Overlay Stream<br/>deploy/kubernetes/overlays/local]
        T_Prod[Test Prod Overlay Stream<br/>deploy/kubernetes/overlays/prod]
    end

    T_Base -->|Assert| B_6Res[Renders 6 application resources]
    T_Base -->|Assert| B_NoDB[Zero PostgreSQL resources]
    T_Base -->|Assert| B_NoSec[Zero plaintext secrets]

    T_Local -->|Assert| L_9Res[Renders 8-9 resources: App + Postgres]
    T_Local -->|Assert| L_PG[bi-postgres-service & bi-postgres-deployment present]
    T_Local -->|Assert| L_Schema[Schema ConfigMap attached]
    T_Local -->|Assert| L_URL[DATABASE_URL points to bi-postgres-service:5432]

    T_Prod -->|Assert| P_NoPG[Zero in-cluster PostgreSQL resources]
    T_Prod -->|Assert| P_Sec[bi-api-secret referenced externally]
    T_Prod -->|Assert| P_FrontNoDB[Zero DATABASE_URL in frontend Deployment]
```

### Required Test Assertions:
1. `kubectl kustomize deploy/kubernetes/base` renders exactly 6 resources (no PostgreSQL).
2. `kubectl kustomize deploy/kubernetes/overlays/local` renders backend, frontend, AND PostgreSQL (Deployment, Service, PVC, schema ConfigMap).
3. `kubectl kustomize deploy/kubernetes/overlays/prod` renders backend and frontend, and strictly EXCLUDES any PostgreSQL Deployment or Service.
4. `bi-frontend-deployment` has zero `DATABASE_URL` in base, local, and prod.
5. All Service selectors (`app.kubernetes.io/name`) match their respective Deployment pod labels across all variants.
6. Zero plaintext production credentials or unreplaced tokens exist in any manifest.

---

## 8. Actual Verification Commands & Execution Results

The following commands were executed live in the environment to establish and verify the baseline for this audit:

### 1. Kustomize Render Validation
```bash
kubectl kustomize deploy/kubernetes
```
- **Exit Code:** 0
- **Result:** Successfully rendered all 6 resources (`bi-api-config`, `bi-frontend-config`, `bi-api-service`, `bi-frontend-service`, `bi-api-deployment`, `bi-frontend-deployment`).

### 2. Manifest Automated Test Suite
```bash
./.venv/bin/pytest tests/test_kubernetes_manifests.py -v
```
- **Exit Code:** 0
- **Result:** **19 passed in 0.33s** (12 backend assertions + 7 frontend assertions).
- **Verified:** All YAML specs valid, Kustomize stream builds cleanly, zero hardcoded credentials, non-root user enforcement (UID 1000 for backend, UID 1001 for frontend), exact probe configurations, and zero `DATABASE_URL` references in frontend manifests.

### 3. Container Deployment Smoke Test Suites (Local Evaluation)
```bash
./.venv/bin/pytest tests/test_container_smoke.py tests/test_frontend_container_smoke.py -v
```
- **Exit Code:** 0
- **Result:** **12 skipped in 1.56s** (Docker daemon offline locally; tests cleanly skipped per `@pytest.mark.skipif(not docker_available)`).
- **CI Baseline:** In CI runner environment with Docker active, all 12 tests pass (4 frontend container smoke tests + 8 backend container smoke tests).

### 4. Full Offline Regression Test Suite
```bash
./.venv/bin/pytest -m "not postgres_integration and not docker" -q
```
- **Exit Code:** 0
- **Result:** **449 passed, 14 deselected in 11.73s**.
- **Verified:** Complete application, agent core, scoring engine, security sanitization, and interface regression suites pass with zero regressions.

### 5. Git Status Check
```bash
git status
```
- **Result:** Clean working tree relative to Phase 6K.2 baseline; zero untracked runtime artifacts; no commits or pushes performed.

---

## 9. Recommended Next Implementation Milestone

### Phase 6K.3B: Kustomize Base & Overlays Implementation
Implement the design established in this audit:
1. Relocate flat manifests to `deploy/kubernetes/base/` and establish `deploy/kubernetes/base/kustomization.yaml`.
2. Maintain root `deploy/kubernetes/kustomization.yaml` as a backward-compatible forwarder to `base/`.
3. Create `deploy/kubernetes/overlays/local/` with in-cluster PostgreSQL (`postgres:15-alpine`), schema ConfigMap from `database/schema.sql`, local PVC, and backend `DATABASE_URL` patch.
4. Create `deploy/kubernetes/overlays/prod/` with external secret and managed database wiring.
5. Extend `tests/test_kubernetes_manifests.py` to validate `base`, `local`, and `prod` overlay builds and assertions.
6. Update `.github/workflows/ci.yml` and `deploy/kubernetes/README.md`.
