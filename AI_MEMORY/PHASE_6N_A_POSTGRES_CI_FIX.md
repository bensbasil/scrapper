# Phase 6N-A — PostgreSQL Integration CI Schema Failure Diagnosis & Resolution

**Status:** Completed  
**Branch:** `main`  
**Target:** GitHub Actions CI (`.github/workflows/ci.yml`)

---

## 1. Confirmed Root Cause with File/Line Evidence

### Root Cause Summary
In `.github/workflows/ci.yml`, the `test-postgres-integration` job defines a service container running `image: postgres:15-alpine` (`POSTGRES_DB: test_db`, `POSTGRES_USER: test_user`). However, prior to this fix, the workflow never applied the canonical schema file ([`database/schema.sql`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/schema.sql)) to the newly provisioned service database before invoking `pytest -m "postgres_integration" -v`.

Consequently, the PostgreSQL service database was completely empty (0 tables).

### Evidence & Traceback
1. **Canonical Schema Definition:**
   - In [`database/schema.sql:201-216`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/schema.sql#L201-L216), table `pipeline_runs` is canonically defined with column `run_id VARCHAR(100) UNIQUE NOT NULL`.
2. **Workflow Configuration (Before Fix):**
   - In [`.github/workflows/ci.yml:60-102`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml#L60-L102), the job initialized dependencies and ran `pytest -m "postgres_integration"` without applying `database/schema.sql`.
3. **Failing Test Execution in CI:**
   - In [`tests/test_phase6j1_backend_enablers.py:407`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_phase6j1_backend_enablers.py#L407), the test executes initial cleanup:
     ```python
     cur.execute("DELETE FROM pipeline_runs WHERE run_id LIKE 'test-run-%';")
     ```
     Because `pipeline_runs` did not exist in the unseeded CI database, line 407 raised `psycopg2.errors.UndefinedTable: relation "pipeline_runs" does not exist`.
   - Execution jumped immediately to the `finally` cleanup block at [`tests/test_phase6j1_backend_enablers.py:502`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_phase6j1_backend_enablers.py#L502):
     ```python
     cur.execute("DELETE FROM pipeline_runs WHERE run_id LIKE 'test-run-%';")
     ```
     Because the table still did not exist, line 502 raised the unhandled `UndefinedTable` error reported in CI.
4. **Historical Isolation:**
   - Previous CI runs only contained [`tests/test_api_server.py::test_real_postgres_integration`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_api_server.py#L432-L456), which only executed `SELECT 1;` without referencing application tables.
   - When commit `4bd452d` added `test_real_postgres_phase6j1_enablers`, it ran locally against persistent Docker/local instances where `01_schema.sql` had already run via `/docker-entrypoint-initdb.d`, but failed in GitHub Actions because CI lacked the initialization step.

---

## 2. Files Changed and Rationale

| File | Change | Rationale |
|---|---|---|
| [`.github/workflows/ci.yml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/.github/workflows/ci.yml) | Added step `Apply canonical database schema` before running PostgreSQL integration tests | Connects to `localhost:5432` (`test_user`/`test_db`) and applies `database/schema.sql` via `psql -v ON_ERROR_STOP=1`. Guarantees fail-fast behavior if any DDL statement fails, and targets the exact test database. |

### Smallest Correct Fix Analysis
- **No changes to production database behavior:** Application runtime does not execute automatic DDL transactions on startup (retaining Phase 5C performance and concurrency protections).
- **No changes to test fixtures or cleanup queries:** Test queries in `tests/test_phase6j1_backend_enablers.py` are strictly correct and accurately validate repository CRUD on real tables.
- **Zero credential leaks:** Credentials in CI match the public existing mock configuration (`POSTGRES_USER: test_user`, `POSTGRES_PASSWORD: test_password`, `POSTGRES_DB: test_db`) and are passed through `PGPASSWORD` rather than command-line flags.
- **Fail-closed execution:** `-v ON_ERROR_STOP=1` ensures any SQL syntax error, schema error, or network failure fails the CI job with non-zero exit code rather than being swallowed.

---

## 3. Tests Executed and Exact Results

### 1. Reproduction against Empty Database
- **Command:** `createdb test_postgres_ci_validation && pytest tests/test_phase6j1_backend_enablers.py -k test_real_postgres_phase6j1_enablers`
- **Result:** **FAILED** at line 407/502 with `psycopg2.errors.UndefinedTable: relation "pipeline_runs" does not exist` (100% reproduction of CI failure).

### 2. Validation after Applying Canonical Schema
- **Command:** `psql -h localhost -p 5432 -d test_postgres_ci_validation -v ON_ERROR_STOP=1 -f database/schema.sql && pytest tests/test_phase6j1_backend_enablers.py -k test_real_postgres_phase6j1_enablers -v`
- **Result:** **PASSED** [100%] in 0.19s.

### 3. Full Service-Backed PostgreSQL Integration Suite
- **Command:** `pytest -m "postgres_integration" -v`
- **Result:** **2 passed, 472 deselected in 1.39s**.
  - `tests/test_api_server.py::test_real_postgres_integration` **PASSED**
  - `tests/test_phase6j1_backend_enablers.py::test_real_postgres_phase6j1_enablers` **PASSED**

### 4. Full Python Offline Suite (with Unreachable DATABASE_URL Isolation)
- **Command:** `DATABASE_URL="postgresql://ci_isolated:invalid_pass@127.0.0.1:59999/nonexistent" pytest -m "not postgres_integration and not docker" -q`
- **Result:** **460 passed, 14 deselected in 6.47s**.

### 5. Kubernetes Manifest Security & Specification Suite
- **Command:** `pytest tests/test_kubernetes_manifests.py -v`
- **Result:** **30 passed in 0.63s**.

### 6. Git Diff Check
- **Command:** `git diff --check`
- **Result:** Clean exit code 0, zero whitespace or syntax issues.

---

## 4. Checks That Remain Unverified

- **Live GitHub Actions Runner Execution:** Local testing verified `psql -v ON_ERROR_STOP=1` against local PostgreSQL 15 on port 5432 with identical configuration. Actual GitHub Actions execution will run once the commit is pushed to remote.

---

## 5. Safe to Commit Verification

- [x] Confirmed root cause with line-by-line evidence.
- [x] Implemented minimal non-invasive fix without modifying production code or weakening test assertions.
- [x] Validated against real PostgreSQL instance locally.
- [x] Verified full offline test suite (460 passed).
- [x] Preserved zero git commit / push constraint.
