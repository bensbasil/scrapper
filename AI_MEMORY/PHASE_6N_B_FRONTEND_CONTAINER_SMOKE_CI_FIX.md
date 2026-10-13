# Phase 6N-B — Frontend Container Smoke CI Failure Diagnosis & Resolution

**Status:** Completed  
**Branch:** `main`  
**Target:** Next.js Frontend CI Test Runner Configuration (`dashboard/package.json`)

---

## 1. Confirmed Root Cause with File/Line Evidence

### Root Cause Summary
In `.github/workflows/ci.yml`, the `frontend-build` job ("Next.js Frontend Build & Container Smoke Tests") defines sequential steps for testing and container packaging:
1. Step `Run Frontend Tests`: runs `npm test` inside `dashboard/`
2. Step `Build Next.js Dashboard`: runs `npm run build` inside `dashboard/`
3. Step `Build Frontend Docker image`: runs `docker build -t business-intelligence-frontend:ci dashboard`
4. Step `Run Frontend Container Deployment Smoke Tests`: runs `npm run test:smoke` with `FRONTEND_IMAGE_TAG: "business-intelligence-frontend:ci"`

In `dashboard/package.json`, the `"test"` script was configured as:
```json
"test": "node --test tests/*.test.mjs"
```
The wildcard glob `tests/*.test.mjs` matched:
- `tests/apiClient.test.mjs` (21 unit tests)
- `tests/apiProxy.test.mjs` (23 unit tests)
- `tests/containerSmoke.test.mjs` (1 container deployment smoke test suite)

In GitHub Actions runners (`ubuntu-latest`), the Docker engine is running by default. Therefore, in `tests/containerSmoke.test.mjs:67`, `{ skip: !dockerRunning }` evaluated to `false` (i.e. did not skip).

At Step 1 (`Run Frontend Tests`), the Docker image `business-intelligence-frontend:ci` had **not yet been built**. Because `FRONTEND_IMAGE_TAG` was unset, it fell back to `business-intelligence-frontend:test`. Neither image existed on the ephemeral CI runner.

At `tests/containerSmoke.test.mjs:72-76`:
```javascript
execSync(
  `docker run -d --name ${CONTAINER_NAME} -p ${TEST_PORT}:3000 ` +
  `-e PORT=3000 -e HOSTNAME=0.0.0.0 ${IMAGE_TAG}`,
  { stdio: "pipe", encoding: "utf8" }
);
```
Docker failed to find the image locally, attempted and failed to pull from Docker Hub, and threw an error. Execution reached line 79, column 12:
```javascript
assert.fail(`Failed to start frontend container from ${IMAGE_TAG}: ${err.message}`);
```
This triggered `AssertionError [ERR_ASSERTION]: operator: 'fail'`, causing CI to fail with **44 passed, 1 failed out of 45 tests**.

### Why This Passed Locally
On local developer machines:
1. When Docker was stopped, `isDockerAvailable()` returned `false`, and `containerSmoke.test.mjs` was skipped (`44 passed, 0 failed, 1 skipped`).
2. When Docker was running, `business-intelligence-frontend:test` already existed in the workstation's local Docker cache from previous Phase 6G manual builds, allowing the test to pass against stale local layers.
On a fresh GitHub Actions CI runner, Docker is active, but local images are absent prior to the build step.

---

## 2. Files Changed and Rationale

| File | Change | Rationale |
|---|---|---|
| [`dashboard/package.json`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/package.json) | Changed `"test"` script from `node --test tests/*.test.mjs` to `node --test tests/apiClient.test.mjs tests/apiProxy.test.mjs` | Restores separation between unit test execution (`npm test`) and container deployment smoke test execution (`npm run test:smoke`). Guarantees unit tests run without requiring a pre-built Docker image. |
| [`dashboard/tests/apiClient.test.mjs`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/tests/apiClient.test.mjs) | Added regression test validating `package.json` script isolation | Guarantees `"test"` script never globs or directly executes `containerSmoke`, and guarantees `"test:smoke"` targets `containerSmoke.test.mjs`. |

### Smallest Correct Fix Analysis
- **Zero weakening of smoke test assertions:** [`dashboard/tests/containerSmoke.test.mjs`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/tests/containerSmoke.test.mjs) remains 100% untouched. The critical assertion `assert.fail(...)` on line 79 was not modified, deleted, weakened, or bypassed. When `npm run test:smoke` runs without an image or if container launch fails, it continues to fail loudly as intended.
- **Workflow alignment:** Matches the CI design in `.github/workflows/ci.yml` where Step 1 executes unit tests (`npm test`) and Step 4 executes container smoke tests (`npm run test:smoke`) *after* the Docker image is built.
- **Zero credential leaks:** No tokens or secrets added.

---

## 3. Tests Executed and Exact Results

### 1. Reproduction of CI Failure (Simulating Missing Docker Image)
- **Command:** `cd dashboard && FRONTEND_IMAGE_TAG=business-intelligence-frontend:nonexistent npm test` (before fix)
- **Result:** **FAILED** at line 79, column 12 with `AssertionError [ERR_ASSERTION]: operator: 'fail'`. Exactly 44 passed, 1 failed out of 45 tests (100% exact reproduction).

### 2. Frontend Unit Test Suite (`npm test`) Post-Fix
- **Command:** `cd dashboard && npm test`
- **Result:** **45 passed, 0 failed in 154ms** (22 tests in `apiClient.test.mjs`, 23 tests in `apiProxy.test.mjs`).

### 3. Frontend Unit Test Suite with Nonexistent Docker Image Tag
- **Command:** `cd dashboard && FRONTEND_IMAGE_TAG=business-intelligence-frontend:nonexistent npm test`
- **Result:** **45 passed, 0 failed in 145ms**. Confirms complete decoupling of unit tests from Docker daemon state or image availability.

### 4. Container Smoke Test Suite Negative Validation
- **Command:** `cd dashboard && FRONTEND_IMAGE_TAG=business-intelligence-frontend:nonexistent npm run test:smoke`
- **Result:** **FAILED** cleanly at line 79 with `AssertionError: Failed to start frontend container...`. Confirms the assertion is fully active and not bypassed.

### 5. Multi-Stage Docker Image Build
- **Command:** `docker build -t business-intelligence-frontend:ci dashboard`
- **Result:** **SUCCESS** (Exit code 0, 18 build steps finished, multi-stage Alpine standalone image created).

### 6. Node-Native Container Smoke Test Suite (`npm run test:smoke`)
- **Command:** `cd dashboard && FRONTEND_IMAGE_TAG="business-intelligence-frontend:ci" npm run test:smoke`
- **Result:** **5 passed, 0 failed in 1590ms** (1 suite, 4 subtests: root 200 HTML, non-root user 1001, secret/test exclusion, proxy fail-closed).

### 7. Python Frontend Container Smoke Test Suite
- **Command:** `FRONTEND_IMAGE_TAG="business-intelligence-frontend:ci" ./.venv/bin/pytest tests/test_frontend_container_smoke.py -v`
- **Result:** **4 passed in 1.28s**.

### 8. Python Backend Container Smoke Test Suite
- **Command:** `./.venv/bin/pytest tests/test_container_smoke.py -v`
- **Result:** **8 passed in 1.90s**.

### 9. Python Offline Test Suite (Isolated from DB)
- **Command:** `DATABASE_URL="postgresql://ci_isolated:invalid_pass@127.0.0.1:59999/nonexistent" ./.venv/bin/pytest -m "not postgres_integration and not docker" -q`
- **Result:** **460 passed, 14 deselected in 8.69s**.

### 10. Kubernetes Manifest Security & Specification Suite
- **Command:** `./.venv/bin/pytest tests/test_kubernetes_manifests.py -v`
- **Result:** **30 passed in 0.66s**.

---

## 4. Checks That Remain Unverified

- **Remote GitHub Actions Runner Execution:** Validated locally on Darwin/arm64 workstation with Node 26 and Docker Desktop 29.8.2. Actual remote execution on GitHub Actions runner (`ubuntu-latest`) will occur once changes are committed and pushed by the user.

---

## 5. Safe to Commit Verification

- [x] Confirmed root cause with exact file, line, and test count evidence.
- [x] Implemented smallest correct fix in `dashboard/package.json` without touching production code.
- [x] Preserved smoke test assertions in `dashboard/tests/containerSmoke.test.mjs` untouched without weakening or skipping.
- [x] Added automated architectural regression test in `dashboard/tests/apiClient.test.mjs`.
- [x] Re-validated both unit and container smoke suites locally.
- [x] Verified zero commit/push automatic actions performed.
