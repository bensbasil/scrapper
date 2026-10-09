# Phase 6B — Kubernetes Replica Safety & Runtime Validation Report

**Date:** 2026-10-10  
**Role:** Senior Platform Engineer  
**Source of Truth:** [`AI_MEMORY/PHASE_6A_KUBERNETES_FOUNDATION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6A_KUBERNETES_FOUNDATION.md), [`AI_MEMORY/PHASE_6_EXECUTION.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/AI_MEMORY/PHASE_6_EXECUTION.md)  
**Status:** Complete  

---

## 1. Executive Summary

Phase 6B conducted an architectural audit of multi-replica safety for the Business Opportunity Intelligence Platform API and verified the deployment contract under local constraints.

The audit revealed that the current application architecture relies heavily on host-bound, process-local in-memory state:
- Scraper subprocess control (`running_process`, `process_lock`, `/api/scrape`, `/api/stop`, `/api/status`)
- Real-time log streaming buffer (`log_history`, `log_queues`, `/api/logs`)
- Agent task result lookup registry (`agent_task_store`, `/api/agent/tasks/{task_id}`)
- Observability execution traces (`InMemoryTelemetrySink`)

Deploying multiple replicas behind a round-robin Kubernetes `ClusterIP` Service without a shared persistence layer or distributed coordinator causes immediate client-observable inconsistencies, including intermittent 404s on task lookups, desynchronized scraper controls, empty SSE log streams, and duplicate scraping subprocesses.

**Decision:** The pilot Kubernetes deployment model is explicitly configured to **one replica (`replicas: 1`)**. This provides strong consistency, predictable resource utilization, and prevents race conditions while retaining Kubernetes' core operational advantages (liveness auto-recovery, node rescheduling, and zero-downtime rolling updates).

---

## 2. Multi-Replica Correctness Audit

Each architectural dimension was evaluated against a multi-replica topology behind a round-robin `ClusterIP` Service:

| Area | Implementation & Mechanism | Multi-Replica Behavior & Risk | Classification |
| :--- | :--- | :--- | :--- |
| **Agent Task Lookup & Retention** | In-memory `agent_task_store: Dict[str, AgentExecutionResponse]` and `deque(maxlen=200)` in [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L141). | `POST /api/agent/run` stores results on Pod A. Subsequent `GET /api/agent/tasks/{id}` routed to Pod B returns **HTTP 404 Not Found**. | **Defect for multi-replica; Acceptable limitation for 1-replica pilot** |
| **Scraper Process Control** | Process-local `running_process` and `is_scraper_running()` in [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L137). | Starting a scrape on Pod A leaves Pod B reporting `is_running: false`. Client calling `POST /api/stop` on Pod B fails to stop Pod A. | **Defect for multi-replica; Safe for 1-replica pilot** |
| **Real-time Log Streaming** | Process-local `log_history` deque and `log_queues` in [`api_server.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/api_server.py#L135). | Client connects to `/api/logs` on Pod B while Pod A executes the scraper. Client receives zero log output. | **Defect for multi-replica; Safe for 1-replica pilot** |
| **Agent Telemetry & Observability** | In-memory `InMemoryTelemetrySink` ring buffers in [`agent/telemetry.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/agent/telemetry.py#L175). | Telemetry traces are segregated across pods. Inspections on Pod A cannot observe runs completed on Pod B. | **Acceptable limitation for 1-replica pilot** |
| **Concurrent Work & Duplicate Runs** | Process-local `process_lock = asyncio.Lock()`. | Because the lock is process-local, two clients sending concurrent `POST /api/scrape` for identical queries would spawn concurrent scraper subprocesses on separate pods. | **Defect for multi-replica; Safe for 1-replica pilot** |
| **Database Pool Sizing** | `DB_POOL_MIN=1`, `DB_POOL_MAX=10` per pod via `BoundedConnectionPool` in [`database/db.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/database/db.py#L100). | Each replica claims up to 10 connections. With 1 replica: exactly 1–10 connections. With N replicas: N to 10*N connections against PostgreSQL limit. | **Safe as implemented for 1-replica pilot; requires PgBouncer for horizontal scaling** |
| **Shared Filesystem Assumptions** | Writes to container-local `/app/logs` and `/app/data`. | No shared PVC or cluster filesystem assumptions. Each pod has independent local disk layers. | **Safe as implemented** |
| **Successive Request Inconsistency** | Round-robin distribution of API calls. | Clients polling `/api/status`, `/api/logs`, or `/api/agent/tasks/{id}` observe alternating contradictory states across pods. | **Defect for multi-replica; Eliminated by 1-replica pilot** |

---

## 3. Chosen Pilot Deployment Model

### Model: Single Replica (`replicas: 1`)

### Rationale:
1. **Architectural Honesty:** Specifying `replicas: 2` would provide an illusion of high availability while breaking fundamental client contracts (50% error rate on task lookups and broken log streams).
2. **State Consistency:** With a single replica, all requests hit the same memory space. `agent_task_store`, `running_process`, `log_history`, and telemetry are 100% consistent.
3. **No Duplicate Execution:** Process lock safely prevents overlapping scraping jobs without requiring distributed lock infrastructure (e.g. Redis Redlock).
4. **Predictable Database Footprint:** Exactly 1 to 10 PostgreSQL connections consumed, well within the smallest cloud database tiers.
5. **Zero Additional Infrastructure:** Avoids prematurely introducing Redis, Celery/RabbitMQ, PgBouncer, or shared storage during the initial deployment phase.

### Kubernetes Guarantees Under `replicas: 1`:
Even with a single replica, Kubernetes provides substantial production resilience:
- **Process Liveness Recovery:** If Uvicorn or the event loop crashes or hangs, Kubernetes restarts the container automatically via `/api/health/live`.
- **Node Self-Healing:** If the underlying node fails, the Kubernetes control plane reschedules the pod onto an operational node.
- **Zero-Downtime Rollouts:** Configured with `RollingUpdate` (`maxSurge: 1`, `maxUnavailable: 0`), ensuring a new pod is fully warmed up and passing readiness before the old pod receives `SIGTERM`.

---

## 4. Manifest Changes

Updated [`deploy/kubernetes/deployment.yaml`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/deployment.yaml):
```yaml
spec:
  # Phase 6B Pilot Model: Single replica deployment (replicas: 1).
  # Architectural Rationale:
  # The API server uses in-process host memory for agent task queries (/api/agent/tasks/{id}),
  # log streaming (/api/logs), telemetry deques, and local subprocess tracking (running_process).
  # Running multiple uncoordinated replicas behind a round-robin ClusterIP service causes
  # task lookup 404s, fractured log streams, and duplicate uncoordinated scraping subprocesses.
  # A single replica provides strong consistency, deterministic resource bounding, and full
  # platform stability while still benefiting from Kubernetes container self-healing and rescheduling.
  replicas: 1
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

Updated [`deploy/kubernetes/README.md`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/deploy/kubernetes/README.md) to document the single-replica pilot topology and multi-replica safety requirements.

---

## 5. Runtime Validation Status

### 5.1 Local Environment Audit
- **`kubectl` Client:** Installed (`v1.36.1`).
- **Cluster Status:** No local Kubernetes daemon (Minikube, Kind, or Docker Desktop Kubernetes) was active (`localhost:8080 connection refused`).
- **Policy Compliance:** No unauthorized system changes or cloud services were created.

### 5.2 Verification Completed
1. **Static Kustomize Build:** `kubectl kustomize deploy/kubernetes` executed cleanly (exit code 0), emitting valid KRM with `replicas: 1`.
2. **Automated Manifest & Replica Safety Suite ([`tests/test_kubernetes_manifests.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_kubernetes_manifests.py)):**
   - Verified 11 test cases including `test_deployment_spec_and_replicas` (asserting `replicas == 1`) and `test_multi_replica_state_isolation_risk_demonstration`.
   - **Result:** **11 passed in 0.13s**.
3. **Container Smoke Tests ([`tests/test_container_smoke.py`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/tests/test_container_smoke.py)):**
   - **Result:** **8 passed in 2.02s**.
4. **Full Offline Test Suite:**
   - **Result:** **422 passed, 9 deselected in 7.43s** with dead `DATABASE_URL`.

### 5.3 Runtime Validation (Pending Live Cluster)
When a live cluster (e.g. Kind or staging EKS/GKE) is available, run:
```bash
# 1. Provision secret
kubectl create secret generic bi-api-secret --from-literal=API_AUTH_TOKEN="test-token-123"

# 2. Deploy
kubectl apply -k deploy/kubernetes/

# 3. Verify single pod rollout
kubectl rollout status deployment/bi-api-deployment
kubectl get pods -l app.kubernetes.io/name=business-intelligence-api

# 4. Port-forward and test endpoints
kubectl port-forward svc/bi-api-service 8000:8000
curl http://localhost:8000/api/health/live
curl http://localhost:8000/api/health/ready
```

---

## 6. Path to Multi-Replica Scaling (Future Evolution)

To safely scale beyond 1 replica in future phases, the following architectural components should be introduced:
1. **External Task Storage:** Store agent execution tasks in PostgreSQL or Redis rather than in-memory `agent_task_store`.
2. **Distributed Scraper Coordination:** Move scraping from local `subprocess.Popen` to background worker pods (e.g. via Celery/Redis, RQ, or Kubernetes Jobs) with a distributed lock (e.g. Redis Redlock or Postgres advisory locks).
3. **Centralized Log Streaming:** Stream scraping logs to a pub/sub topic (Redis Pub/Sub or WebSocket gateway) instead of process-local `asyncio.Queue`.
4. **Connection Pooling:** Introduce PgBouncer between Kubernetes pods and PostgreSQL to multiplex database connections.
