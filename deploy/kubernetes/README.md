# Kubernetes Deployment Guide: Business Opportunity Intelligence API

This directory contains minimal, production-minded Kubernetes manifests for running the Business Opportunity Intelligence API in a containerized cluster environment.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |       Ingress / Port-Forward          |
                      +-------------------+-------------------+
                                          |
                                          v
                      +-------------------+-------------------+
                      |   ClusterIP Service: bi-api-service   |
                      |               (Port 8000)             |
                      +-------------------+-------------------+
                                          |
                                          v
                              +-----------------------+
                              | Pod: bi-api-dep-...   |
                              |  - Uvicorn (Non-root) |
                              |  - Liveness: /live    |
                              |  - Readiness: /ready  |
                              |  - Host In-Memory:    |
                              |    - Scraper process  |
                              |    - Task lookup      |
                              |    - SSE log buffer   |
                              +-----------+-----------+
                                          |
                                          v
                      +-------------------+-------------------+
                      | External PostgreSQL Database (Cloud / |
                      |    Dedicated Managed Instance)        |
                      +---------------------------------------+
```

### Components:
- **`bi-api-config` (ConfigMap):** Non-sensitive application configuration (`PORT`, `PYTHONUNBUFFERED`, `ALLOWED_ORIGINS`, connection pool settings).
- **`bi-api-secret` (Secret):** Sensitive credentials (`API_AUTH_TOKEN`, `DATABASE_URL`, `GEMINI_API_KEY`).
- **`bi-api-deployment` (Deployment):** Single-replica deployment (`replicas: 1`) for consistent pilot operation. Configured with unprivileged security context (`appuser` UID 1000), CPU/memory bounds (100m–1000m CPU, 256Mi–512Mi RAM), startup/liveness/readiness probes, and 30-second graceful termination.
- **`bi-api-service` (Service):** Internal `ClusterIP` load balancer directing traffic to the ready pod on port 8000.

### Note on Multi-Replica Safety & Rollout Strategy (Phases 6B & 6C):
The API application utilizes in-memory process state for:
1. Agent task result lookup (`/api/agent/tasks/{task_id}`).
2. Scraper process management (`running_process`, `/api/scrape`, `/api/stop`, `/api/status`).
3. Real-time log streaming (`/api/logs` via process-local queues).
4. Telemetry traces (`InMemoryTelemetrySink`).

#### 1. Why the Pilot Uses One Replica:
Running multiple uncoordinated replicas behind a round-robin Service causes state fragmentation:
- 50% chance of `HTTP 404` when polling `/api/agent/tasks/{id}`.
- Contradictory scraper status and broken SSE log streams across pods.
- Risk of concurrent uncoordinated scraping subprocesses on identical search queries.
A single replica (`replicas: 1`) guarantees strict state consistency, deterministic connection pool limits (1–10 DB connections), and eliminates race conditions.

#### 2. Why the Rollout Strategy is 'Recreate':
Standard Kubernetes `RollingUpdate` with `maxSurge: 1` spins up the replacement pod while the old pod is still running. For an application with host-bound subprocesses and in-memory state, this surge window breaks single-replica safety during updates (dual scraper executions, split-brain task lookups, and double DB connection pool allocations).
The `Recreate` strategy terminates the old pod first, allowing its `@app.on_event("shutdown")` handler to cleanly stop active scraper processes and close connection pools before the new pod is created.

#### 3. Expected Downtime During Updates:
With `strategy: type: Recreate`, there is a brief, deterministic downtime window of **~5–15 seconds** while the existing pod terminates, the new pod is scheduled, and the new container passes its startup probe. Zero-downtime deployment is explicitly not claimed until external state brokers and worker queues are implemented.

#### 4. What Happens to In-Memory Tasks & Telemetry on Restart:
- **In-Memory State:** `agent_task_store` (last 200 agent results), `log_history` buffer, and `InMemoryTelemetrySink` ring buffers reside strictly in container RAM and are reset upon pod termination.
- **Persistent State:** Enriched business entities, discovery sources, outreach drafts, and pipeline run logs stored in PostgreSQL survive pod restarts and remain fully accessible via protected endpoints.

---

## Prerequisites

1. Kubernetes cluster (v1.24+) accessible via `kubectl`.
2. Built container image tagged and pushed to an accessible registry (e.g. `business-intelligence-api:latest`).

---

## Deployment Steps

### 1. Provision Secrets
Never commit secrets into git. Generate and create the `bi-api-secret` out-of-band:

```bash
# 1. Generate strong API auth token
AUTH_TOKEN=$(openssl rand -hex 32)

# 2. Create the Kubernetes Secret (Standalone Mode - no database)
kubectl create secret generic bi-api-secret \
  --from-literal=API_AUTH_TOKEN="${AUTH_TOKEN}"

# OR: Create with external PostgreSQL and Gemini LLM provider credentials
kubectl create secret generic bi-api-secret \
  --from-literal=API_AUTH_TOKEN="${AUTH_TOKEN}" \
  --from-literal=DATABASE_URL="postgresql://bi_user:strong_pass@postgres-host:5432/bi_db" \
  --from-literal=GEMINI_API_KEY="AIzaSyYourSecretKey"
```

### 2. Apply Kubernetes Manifests

```bash
# Apply using Kustomize
kubectl apply -k deploy/kubernetes/
```

### 3. Verify Deployment & Pod Status

```bash
# Check rollout status
kubectl rollout status deployment/bi-api-deployment

# Inspect pods, labels, and readiness
kubectl get pods -l app.kubernetes.io/name=business-intelligence-api -o wide

# Check service endpoint resolution
kubectl get endpoints bi-api-service
```

---

## Health Check & Probe Semantics

| Probe | Path | Port | Interval | Failure Threshold | Behavioral Contract |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Startup** | `/api/health/live` | `http` (8000) | 5s (delay 2s) | 6 | Protects slow cold starts during module loading. |
| **Liveness** | `/api/health/live` | `http` (8000) | 10s | 3 | Checks process responsiveness. Zero database/LLM dependencies. Restarts hung processes. |
| **Readiness** | `/api/health/ready` | `http` (8000) | 10s | 2 | Checks subsystem status. Returns 200 in standalone mode. Returns 503 if configured DB fails. Pulls unready pods out of service endpoints without restarting the container. |

---

## Local Verification & Port-Forwarding

```bash
# Forward local port 8000 to the service
kubectl port-forward svc/bi-api-service 8000:8000

# Test Liveness probe
curl -i http://localhost:8000/api/health/live

# Test Readiness probe
curl -i http://localhost:8000/api/health/ready

# Test Protected Endpoint without token (Expect 401 Unauthorized)
curl -i http://localhost:8000/api/businesses

# Test Protected Endpoint with token
curl -i -H "X-API-Key: ${AUTH_TOKEN}" http://localhost:8000/api/businesses
```

---

## Inspection & Troubleshooting

```bash
# Inspect pod events and probe failures
kubectl describe pod -l app.kubernetes.io/name=business-intelligence-api

# View streaming logs
kubectl logs -l app.kubernetes.io/name=business-intelligence-api -c api -f
```

---

## Rollout Management & Rollback

```bash
# Check rollout status and progress
kubectl rollout status deployment/bi-api-deployment

# View deployment rollout revision history
kubectl rollout history deployment/bi-api-deployment

# Roll back to previous revision if an update fails or regresses
kubectl rollout undo deployment/bi-api-deployment

# Trigger a restart (terminates old pod, executes graceful shutdown, starts replacement)
kubectl rollout restart deployment/bi-api-deployment
```

---

## Teardown & Cleanup

```bash
# Delete all resources created by manifests
kubectl delete -k deploy/kubernetes/

# Delete the secret
kubectl delete secret bi-api-secret
```
