# Phase 6C — Single-Replica Kubernetes Rollout Safety Report

**Date:** 2026-10-10  
**Role:** Senior Platform Engineer  
**Source of Truth:** [`AI_MEMORY/PHASE_6A_KUBERNETES_FOUNDATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6A_KUBERNETES_FOUNDATION.md), [`AI_MEMORY/PHASE_6B_REPLICA_SAFETY.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6B_REPLICA_SAFETY.md), [`AI_MEMORY/PHASE_6_EXECUTION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6_EXECUTION.md)  
**Status:** Complete  

---

## 1. Executive Summary

Phase 6C addresses a subtle but dangerous failure mode in Kubernetes deployments of stateful, host-bound applications: **simultaneous pod surge during deployment updates**.

Although Phase 6B correctly reduced the steady-state replica count to `replicas: 1`, the default rollout strategy (`RollingUpdate` with `maxSurge: 1`, `maxUnavailable: 0`) allowed Kubernetes to spin up a new replacement pod while the old pod was still running. During image or configuration updates, two pods would coexist for up to 30 seconds. In our host-bound architecture, this surge window introduces split-brain scraper subprocesses, dual database pool allocations, and fragmented in-memory task lookups.

**Remediation:** Configured the deployment rollout strategy to **`Recreate`** (`strategy.type: Recreate`). This guarantees strict mutual exclusion: the existing pod is fully stopped and its resources cleaned up before the replacement pod is scheduled and started. The trade-off is an acknowledged, deterministic downtime window of ~5–15 seconds during updates.

---

## 2. Rollout Semantics Evaluation: `RollingUpdate` vs `Recreate`

### 2.1 The Failure Mode of `RollingUpdate` with `maxSurge: 1`
Under `RollingUpdate` with `maxSurge: 1, maxUnavailable: 0` on a 1-replica deployment:
1. When an update is initiated (e.g., image change or configmap update), Kubernetes schedules Pod B (new replica).
2. Pod B pulls the image, starts the container, and begins probe evaluation.
3. Throughout this entire warmup window (~15–30 seconds), **both Pod A and Pod B are simultaneously running**:
   - **Conflicting Scraper Operations:** If a user initiates a crawl or if Pod A was actively scraping, two scraping subprocesses can run concurrently against the same targets.
   - **Split-Brain Task Stores:** Requests routed between the terminating and starting pod produce contradictory `GET /api/agent/tasks/{id}` 404s.
   - **Database Connection Pool Contention:** Two pools of up to 10 connections each contend for PostgreSQL connection capacity (up to 20 connections).
4. `RollingUpdate` provides the illusion of zero-downtime while breaking the single-replica safety invariant at the most critical operational moment: an update rollout.

### 2.2 Why `Recreate` is the Only Safe Pilot Strategy
Under `strategy: type: Recreate`:
1. Kubernetes terminates Pod A first.
2. Pod A receives `SIGTERM` and initiates its graceful shutdown handler (`shutdown_event` in [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L474-L508)):
   - Active scraper subprocesses receive `terminate()`, wait 1s, and escalate to `kill()`.
   - PostgreSQL connection pool is cleanly and idempotently closed via `db_manager.close()`.
3. Pod A exits completely within `terminationGracePeriodSeconds: 30`.
4. Only after Pod A has terminated does Kubernetes schedule Pod B.
5. **Guarantee:** At NO point in time do two application pods run concurrently.

### 2.3 Explicit Trade-off: Acknowledged Downtime
- With `Recreate`, clients experience a temporary downtime window of approximately **5–15 seconds** during application rollouts.
- During this window, requests to the Service receive connection resets or HTTP 503 until Pod B passes its `startupProbe` and `readinessProbe`.
- **Engineering Stance:** We explicitly acknowledge this temporary downtime trade-off. For a pilot system with in-memory task state and host-bound scraping, deterministic downtime during updates is vastly superior to silent data corruption, duplicate crawls, and split-brain state.

---

## 3. Shutdown and Startup Interaction

### 3.1 Termination Lifecycle
In [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L474-L508):
```python
@app.on_event("shutdown")
async def shutdown_event():
    global running_process
    # 1. Terminate any active scraper subprocess
    if running_process is not None:
        try:
            ...
            running_process.terminate()
            await asyncio.sleep(1)
            ...
            running_process.kill()
        finally:
            running_process = None

    # 2. Close database connection pool safely and idempotently
    try:
        db_manager.close()
        logger.info("[System] Database connection pool closed on server shutdown.")
    except Exception as e:
        logger.warning(f"Error closing database pool on shutdown: {e}")
```
- In [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml), `terminationGracePeriodSeconds: 30` provides ample headroom for this cleanup (which takes ~1.5–3 seconds), ensuring the container exits cleanly before Kubelet escalates to SIGKILL.

### 3.2 Startup Lifecycle & Probe Sequencing
- **`startupProbe`:** Configured with `initialDelaySeconds: 2`, `periodSeconds: 5`, `failureThreshold: 6`. Grants up to 32 seconds for Python imports, Uvicorn binding, and event loop initialization before liveness checks engage.
- **`livenessProbe`:** Targets `/api/health/live` on port `http` every 10s (sub-millisecond, zero DB/LLM dependency).
- **`readinessProbe`:** Targets `/api/health/ready` on port `http` every 10s. Service only directs traffic to the replacement pod once readiness returns 200 OK.

### 3.3 In-Memory State on Pod Restart
- **Reset In-Memory State:** Process-local `agent_task_store` (last 200 results), `log_history` buffer, and `InMemoryTelemetrySink` ring buffers reside in RAM and are reset upon pod recreation.
- **Preserved Persistent State:** Discovered business entities, outreach drafts, enriched metadata, and pipeline run history in PostgreSQL survive pod recreation.

---

## 4. Manifest Updates

Updated [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml):
```yaml
spec:
  replicas: 1
  # Phase 6C Rollout Strategy: Recreate
  # Architectural Rationale:
  # The application maintains process-local in-memory state and launches uncoordinated
  # scraping subprocesses on the local host. A RollingUpdate with maxSurge: 1 would spin up
  # a new pod while the old pod is still running, violating single-replica mutual exclusion
  # during rollouts and risking split-brain scraping and dual database pool connections.
  # The 'Recreate' strategy terminates the existing pod and waits for complete process
  # exit and resource cleanup before creating the replacement pod.
  # Trade-off: A brief, deterministic downtime window (~5-15 seconds) occurs during rollouts.
  # Zero-downtime deployment is explicitly not claimed until external state coordination is introduced.
  strategy:
    type: Recreate
```

Updated [`deploy/kubernetes/README.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/README.md):
- Detailed the 4-part architectural rationale for `replicas: 1` and `strategy: Recreate`.
- Documented expected downtime (~5–15s) and in-memory vs persistent data lifecycle.
- Added operator commands for rollout inspection (`rollout status`, `rollout history`), rollbacks (`rollout undo`), and restarts (`rollout restart`).

---

## 5. Automated Verification & Test Results

### 5.1 Automated Manifest Tests ([`tests/test_kubernetes_manifests.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_kubernetes_manifests.py))
- Updated `test_deployment_spec_and_replicas` to assert `replicas == 1` and `strategy.type == "Recreate"`.
- Added `test_rollout_strategy_strictly_prohibits_simultaneous_pods` verifying that `strategy.type == "Recreate"`, `rollingUpdate` is not present, and `terminationGracePeriodSeconds >= 30`.
- **Result:** **12 passed in 0.08s**.

### 5.2 Static Kustomize Build
- Validated via `kubectl kustomize deploy/kubernetes`. Output cleanly reflects `replicas: 1` and `strategy: type: Recreate`.
- **Disclaimer:** A successful Kustomize build verifies static syntax and resource generation; it is not proof of cluster runtime behavior.

### 5.3 Full Offline Test Suite
- **Command:** `DATABASE_URL="postgresql://user:pass@127.0.0.1:59999/nonexistent" ./.venv/bin/pytest -m "not postgres_integration and not docker" -q`
- **Result:** **424 passed, 9 deselected in 7.80s** with intentionally dead database.

---

## 6. Rollout Management Commands

```bash
# Check rollout progress (shows pod termination, then recreation)
kubectl rollout status deployment/bi-api-deployment

# View rollout history revisions
kubectl rollout history deployment/bi-api-deployment

# Roll back to previous revision if needed
kubectl rollout undo deployment/bi-api-deployment

# Trigger a clean restart with graceful shutdown and recreation
kubectl rollout restart deployment/bi-api-deployment
```

---

## 7. Remaining Limitations & Next Steps

1. **Horizontal Scaling Roadmap:** To evolve from the single-replica `Recreate` model to multi-replica zero-downtime `RollingUpdate`, the platform requires:
   - External state storage (PostgreSQL/Redis) for agent task responses.
   - Dedicated background workers (Celery/RQ/Kubernetes Jobs) decoupled from HTTP request serving.
   - Distributed locking for scraping tasks (e.g. Postgres advisory locks or Redis Redlock).
   - Centralized pub/sub log streaming.
2. **Current Pilot Safety:** Within the scope of the pilot platform, `replicas: 1` with `strategy: Recreate` provides complete operational safety, bounded resources, and predictable lifecycle management.
