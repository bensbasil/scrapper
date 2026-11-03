# Phase 6N-F.2: Migration Deployment Integration Report

**Project:** Business Opportunity Intelligence Platform  
**Repository:** `scrapper`  
**Date:** 2026-10-24  
**Implementation Phase:** Phase 6N-F.2 (Migration Deployment Integration into CI & Kubernetes)  
**Baseline Commit:** `11b6c92` (*feat(db): implement versioned migration runner foundation with schema isolation (Phase 6N-F.1)*)  
**Status:** **COMPLETE, VERIFIED & PASSING**  

---

## 1. Executive Summary

Phase 6N-F.2 integrates the deterministic, versioned PostgreSQL migration runner developed in Phase 6N-F.1 (`database/migrate.py`) into both the continuous integration pipeline (`.github/workflows/ci.yml`) and declarative production Kubernetes manifests (`deploy/kubernetes/`).

Key achievements in this phase:
1. **CI Pipeline Hardening:** Replaced legacy unversioned `psql -f database/schema.sql` bootstrapping in GitHub Actions with `python -m database.migrate` and automated idempotency verification via `python -m database.migrate --check`.
2. **Declarative Kubernetes Migration Job:** Authored `deploy/kubernetes/base/migration-job.yaml` specifying a dedicated `batch/v1` `Job` (`bi-db-migration`) that runs non-root (UID 1000) using the same application image and Python environment as the backend API.
3. **Kustomize Integration:** Added `migration-job.yaml` to `deploy/kubernetes/base/kustomization.yaml`. Image tag transformers in `deploy/kubernetes/overlays/prod/kustomization.yaml` automatically tag the Job with the target production release tag (`v1.0.0`). Local overlay remains 100% usable via `bi-api-secret`.
4. **Explicit Release-Gating Sequence:** Documented and established the staged release execution model that enforces waiting for migration Job success (`kubectl wait --for=condition=complete`) before promoting or rolling out the API Deployment (`bi-api-deployment`).
5. **Zero Credential Exposure:** Database passwords are never passed as CLI arguments or logged; all connection strings are scrubbed via `sanitize_db_url`.

---

## 2. CI Migration Workflow & Idempotency Verification

In `.github/workflows/ci.yml`, within the `test-postgres-integration` job:

### Previous Configuration (Legacy):
```yaml
- name: Apply canonical database schema
  env:
    PGPASSWORD: test_password
  run: |
    psql -h localhost -U test_user -d test_db -v ON_ERROR_STOP=1 -f database/schema.sql
```

### New Configuration (Phase 6N-F.2):
```yaml
- name: Apply database migrations
  env:
    DATABASE_URL: "postgresql://test_user:test_password@localhost:5432/test_db"
  run: |
    python -m database.migrate

- name: Verify migration idempotency and clean status
  env:
    DATABASE_URL: "postgresql://test_user:test_password@localhost:5432/test_db"
  run: |
    python -m database.migrate --check

- name: Run PostgreSQL integration tests
  env:
    DATABASE_URL: "postgresql://test_user:test_password@localhost:5432/test_db"
    TEST_DATABASE_URL: "postgresql://test_user:test_password@localhost:5432/test_db"
    API_AUTH_TOKEN: "ci-test-token"
  run: |
    pytest -m "postgres_integration" -v
```

### How Idempotency and Integrity Are Checked:
1. `python -m database.migrate` executes:
   - Scopes to `DATABASE_URL` (connecting to `test_db` on PostgreSQL 15).
   - Acquires PostgreSQL session advisory lock (`pg_advisory_lock(hashtext('schema_migrations_public'))`).
   - Ensures `schema_migrations` table exists.
   - Plans pending migrations: identifies `001_initial_schema` (`database/schema.sql`).
   - Executes DDL within an explicit transaction and inserts record with execution time and SHA-256 checksum into `schema_migrations`.
   - Releases advisory lock and commits.
2. `python -m database.migrate --check` immediately verifies idempotency:
   - Inspects `schema_migrations` and verifies that all available migrations are applied.
   - Re-computes SHA-256 checksums to verify zero drift.
   - If pending migrations exist or drift is detected, exits with code 1, immediately failing CI.
   - If clean, outputs `PASSED: Database is fully migrated and clean.` and exits with code 0.
3. `pytest -m "postgres_integration"` executes 10 live database tests across `test_phase6j1_backend_enablers.py`, `test_api_server.py`, and `test_database_migrations.py`.

---

## 3. Production Migration Job Specification

File: [`deploy/kubernetes/base/migration-job.yaml`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/deploy/kubernetes/base/migration-job.yaml)

### Architectural Properties:
- **API Version & Kind:** `batch/v1` `Job`
- **Metadata Name:** `bi-db-migration`
- **Labels:**
  - `app.kubernetes.io/name: business-intelligence-api`
  - `app.kubernetes.io/part-of: business-opportunity-platform`
  - `app.kubernetes.io/component: migration`
- **Finite Execution Bounding:**
  - `backoffLimit: 3`: Retries transient connection blips up to 3 times before failing closed.
  - `activeDeadlineSeconds: 120`: Aborts if execution hangs for > 2 minutes, preventing hung release pipelines.
  - `ttlSecondsAfterFinished: 300`: Kubernetes TTL controller automatically reclaims completed Job pods and resources after 5 minutes, allowing clean re-application on subsequent releases.
- **Security Context (Least Privilege):**
  - Pod: `runAsNonRoot: true`, `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000`, `seccompProfile: {type: RuntimeDefault}`.
  - Container: `allowPrivilegeEscalation: false`, `capabilities: {drop: ["ALL"]}`, `readOnlyRootFilesystem: false`.
- **Resource Constraints:**
  - `requests: {cpu: 100m, memory: 128Mi}`
  - `limits: {cpu: 500m, memory: 256Mi}`
- **Execution Command:**
  - `command: ["python", "-m", "database.migrate"]`
- **Configuration & Credential Wiring:**
  - `envFrom`: ConfigMap `bi-api-config` (shares non-sensitive environment configuration).
  - `env`: `DATABASE_URL` sourced via `secretKeyRef` from `bi-api-secret` (key `DATABASE_URL`). Zero plaintext credentials in manifests.

---

## 4. Production Release-Gating Sequence & Lifecycle Ordering

### Why Gating Is Essential:
In Kubernetes, `kubectl apply` treats all manifests concurrently. If a `Job` and a `Deployment` are applied together in a single `kubectl apply -k` call, the API Deployment immediately starts launching replacement pods while the migration Job pod is still starting.

To guarantee that database migrations complete successfully **before** promoting or starting the new API Deployment version, production release pipelines must follow this 3-step staged sequence:

```bash
# ------------------------------------------------------------------------------
# STEP 1: Pre-Migration Cleanup
# ------------------------------------------------------------------------------
# Remove completed migration Job from prior release if present
kubectl delete job bi-db-migration --ignore-not-found --wait=true

# ------------------------------------------------------------------------------
# STEP 2: Deploy & Execute Migration Job First
# ------------------------------------------------------------------------------
# Render production overlay and apply strictly the migration Job resource
kubectl kustomize deploy/kubernetes/overlays/prod | kubectl apply -l app.kubernetes.io/component=migration -f -

# Wait for migration Job completion with finite timeout (matching activeDeadlineSeconds: 120s)
echo "Awaiting database migration completion..."
kubectl wait --for=condition=complete --timeout=120s job/bi-db-migration

# RELEASE GATE: If migration fails or times out, kubectl wait exits with a non-zero code.
# The CI/CD release pipeline halts immediately.
# The API Deployment rollout is NEVER triggered, leaving existing running pods intact.

# ------------------------------------------------------------------------------
# STEP 3: Rollout Application Workloads (Executed ONLY after migration success)
# ------------------------------------------------------------------------------
kubectl apply -k deploy/kubernetes/overlays/prod

# Verify rollout status of application pods
kubectl rollout status deployment/bi-api-deployment --timeout=180s
kubectl rollout status deployment/bi-frontend-deployment --timeout=180s
```

---

## 5. Rollback and Failure Behavior

| Scenario | Behavior & Operational Procedure |
|---|---|
| **Migration DDL Failure During Job** | `database/migrate.py` catches execution error, triggers `conn.rollback()` in PostgreSQL, releases advisory locks in `finally`, and exits code 1. Zero partial tables remain. `kubectl wait` returns code 1, halting release. Existing API pods continue serving. |
| **Migration Lock Acquisition Timeout** | If another migration instance holds the advisory lock or statement times out, `apply_pending()` rolls back, logs sanitized error, and fails closed with `MigrationExecutionError`. |
| **Application Deployment Failure After Migration** | If new API pods fail readiness probes (e.g. invalid code change), Kubernetes keeps previous pods running under `Recreate` strategy or aborts rollout. Operator can execute `kubectl rollout undo deployment/bi-api-deployment`. |
| **Schema Backward Compatibility** | All migrations are forward-only and additive (`CREATE TABLE IF NOT EXISTS`, nullable columns). Rolled-back application versions remain fully operational against the forward-migrated database schema. |

---

## 6. Environment Variables and Secrets Inventory

| Variable Name | Sourced From | Purpose | Sensitivity |
|---|---|---|---|
| `DATABASE_URL` | `bi-api-secret` (Key: `DATABASE_URL`) | PostgreSQL connection DSN used by migration runner and API server pool. | **Secret** (sanitized in all logs) |
| `API_AUTH_TOKEN` | `bi-api-secret` (Key: `API_AUTH_TOKEN`) | Constant-time bearer token for API endpoint protection. | **Secret** |
| `GEMINI_API_KEY` | `bi-api-secret` (Key: `GEMINI_API_KEY`) | Google Gemini LLM API credential. | **Secret** |
| `PORT` | `bi-api-config` | API server listen port (default `8000`). | Non-sensitive |
| `PYTHONUNBUFFERED` | `bi-api-config` | Ensures immediate container log flushing. | Non-sensitive |

---

## 7. Automated Test Results and Verification

All test suites were executed directly on the developer host:

### 1. Migration Runner Offline Unit Tests
- **Command:** `.venv/bin/python -m pytest tests/test_database_migrations.py -m "not postgres_integration" -v`
- **Result:** **18 passed, 8 deselected in 0.03s** (100% pass rate).

### 2. Live PostgreSQL Migration Integration Tests
- **Command:** `TEST_DATABASE_URL="postgresql://bistto@localhost:5432/postgres" .venv/bin/python -m pytest tests/test_database_migrations.py -m "postgres_integration" -v`
- **Result:** **8 passed, 18 deselected in 0.38s** (100% pass rate).

### 3. Kubernetes Manifest Security & Specification Tests
- **Command:** `.venv/bin/python -m pytest tests/test_kubernetes_manifests.py -v`
- **Result:** **31 passed in 0.79s** (100% pass rate).
- **New Test Added:** `test_migration_job_spec_and_security_contract` verifying Job limits, non-root UID 1000, drop ALL capabilities, `OnFailure` restart policy, secret wiring, and production image tagging (`business-intelligence-api:v1.0.0`).

### 4. Full Offline Python Regression Suite
- **Command:** `.venv/bin/python -m pytest -m "not postgres_integration and not docker" -q`
- **Result:** **509 passed, 23 deselected in 6.57s** (0 failures, 0 regressions).

### 5. Frontend Unit Test Suite
- **Command:** `npm --prefix dashboard test`
- **Result:** **45 passed in 144ms** (100% pass rate).

### 6. Code Style & Whitespace Check
- **Command:** `git diff --check`
- **Result:** Clean (0 whitespace errors, 0 conflict markers).

### 7. Declarative Kustomize Target Builds
- **Commands:**
  - `kubectl kustomize deploy/kubernetes` -> **Valid**
  - `kubectl kustomize deploy/kubernetes/base` -> **Valid (7 resources)**
  - `kubectl kustomize deploy/kubernetes/overlays/local` -> **Valid (12 resources, in-cluster DB + Job)**
  - `kubectl kustomize deploy/kubernetes/overlays/prod` -> **Valid (7 resources, tagged v1.0.0, zero in-cluster DB)**

### 8. Docker Smoke Tests Status
- **Status:** **UNVERIFIED (Docker daemon is not running on this host)**
- *Note: Marked UNVERIFIED strictly in compliance with prompt constraints. Verified statically that Dockerfile copies application source, includes `database/migrate.py`, and installs locked dependencies).*

---

## 8. Summary of Files Changed

| File | Status | Description |
|---|---|---|
| [`deploy/kubernetes/base/migration-job.yaml`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/deploy/kubernetes/base/migration-job.yaml) | **Created** | Dedicated Kubernetes Job running `python -m database.migrate` with finite limits. |
| [`deploy/kubernetes/base/kustomization.yaml`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/deploy/kubernetes/base/kustomization.yaml) | **Modified** | Added `migration-job.yaml` to base resources. |
| [`.github/workflows/ci.yml`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/.github/workflows/ci.yml) | **Modified** | Replaced `psql` schema load with `python -m database.migrate` and `--check`. |
| [`tests/test_kubernetes_manifests.py`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/tests/test_kubernetes_manifests.py) | **Modified** | Updated resource assertions and added `test_migration_job_spec_and_security_contract`. |
| [`deploy/kubernetes/README.md`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/deploy/kubernetes/README.md) | **Modified** | Added Job to component inventory and documented release-gating sequence. |
| [`AI_MEMORY/PHASE_6N_F2_MIGRATION_DEPLOYMENT_INTEGRATION.md`](file:///Users/bistto/This%20Mac/Bens_Repository/scrapper/AI_MEMORY/PHASE_6N_F2_MIGRATION_DEPLOYMENT_INTEGRATION.md) | **Created** | Comprehensive architectural and deployment documentation. |
