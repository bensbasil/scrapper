# Phase 6K.2: Frontend Kubernetes Manifest Implementation & Test Suite

**Project:** Business Opportunity Intelligence Platform  
**Date:** 2026-10-11  
**Role:** Senior DevOps / Platform Engineer  
**Scope:** Authoring Kubernetes manifests for the Next.js frontend dashboard, integrating into Kustomize, extending automated manifest test assertions, and verifying container smoke and manifest validity.  
**Status:** **COMPLETE & VERIFIED** (Kustomize builds all 6 backend/frontend resources, 19/19 pytest manifest tests pass, 4/4 container smoke tests pass, 44/44 frontend unit tests pass, 449 Python offline tests pass).

---

## 1. Executive Summary

Phase 6K.2 completes the Kubernetes deployment packaging for the Next.js frontend dashboard (`business-intelligence-frontend`). The frontend is now deployable alongside the FastAPI backend API in Kubernetes clusters using standard declarative KRM manifests.

### Architectural Highlights:
1. **In-Cluster DNS Service Routing:**
   The frontend communicates with the backend via internal Kubernetes DNS: `http://bi-api-service:8000`, configured via `bi-frontend-config` ConfigMap.
2. **Server-Side Secret Injection:**
   `API_AUTH_TOKEN` is injected strictly into the server-side container environment from `bi-api-secret`. The Next.js server attaches `X-API-Key` to upstream API calls without exposing tokens to client browser bundles.
3. **Strict Database Decoupling:**
   `DATABASE_URL` is completely absent from all frontend manifests. The frontend relies exclusively on FastAPI for data access.
4. **Least-Privilege Security:**
   Runs as non-root user `nextjs` (UID 1001, GID 1001), disallows privilege escalation, drops all Linux capabilities, and applies the `RuntimeDefault` seccomp profile.
5. **Declarative Multi-Component Kustomize Build:**
   `deploy/kubernetes/kustomization.yaml` renders both backend and frontend components in a single resource stream.

---

## 2. Files Created & Modified

| File | Status | Description |
| :--- | :--- | :--- |
| `deploy/kubernetes/frontend-deployment.yaml` | **Created** | Deployment for `business-intelligence-frontend:latest` (replicas: 1, RollingUpdate, user 1001, bounded resources, HTTP probes). |
| `deploy/kubernetes/frontend-service.yaml` | **Created** | ClusterIP Service on port 3000 targeting container port `http` (3000). |
| `deploy/kubernetes/frontend-configmap.yaml` | **Created** | ConfigMap defining `PORT: "3000"`, `HOSTNAME: "0.0.0.0"`, `NODE_ENV: "production"`, and `API_INTERNAL_URL: "http://bi-api-service:8000"`. |
| `deploy/kubernetes/kustomization.yaml` | **Modified** | Added frontend ConfigMap, Deployment, and Service to `resources`. |
| `deploy/kubernetes/README.md` | **Modified** | Updated architecture diagrams, component inventory, and port-forwarding instructions. |
| `tests/test_kubernetes_manifests.py` | **Modified** | Added 7 dedicated frontend manifest tests (spec, security, resources, probes, secret wiring, ConfigMap, and Service alignment). |

---

## 3. Frontend-to-Backend Service Routing

```mermaid
graph LR
    subgraph Browser Client
        User[Browser Client]
    end

    subgraph Kubernetes In-Cluster Network
        subgraph Frontend Tier
            FESvc[bi-frontend-service :3000<br/>ClusterIP]
            FEPod[bi-frontend-deployment<br/>Next.js Standalone<br/>Port: 3000<br/>UID: 1001]
        end

        subgraph Backend Tier
            BESvc[bi-api-service :8000<br/>ClusterIP]
            BEPod[bi-api-deployment<br/>FastAPI / Uvicorn<br/>Port: 8000<br/>UID: 1000]
        end

        subgraph Shared Credentials
            Secret[(bi-api-secret<br/>API_AUTH_TOKEN)]
        end
    end

    User -->|Port-Forward / Ingress| FESvc
    FESvc --> FEPod
    FEPod -->|API_INTERNAL_URL: http://bi-api-service:8000<br/>Header: X-API-Key| BESvc
    BESvc --> BEPod
    Secret -.->|API_AUTH_TOKEN| FEPod
    Secret -.->|API_AUTH_TOKEN| BEPod
```

- **Client Traffic:** Handled on port 3000 via `bi-frontend-service`.
- **Server-Side API Proxy & SSR Client:** Dispatches HTTP requests to `http://bi-api-service:8000` via Kubernetes CoreDNS service resolution.
- **Header Injection:** Next.js server components and `apiProxy.ts` attach `X-API-Key: ${API_AUTH_TOKEN}` server-side.

---

## 4. Secret & Configuration Handling

1. **`bi-frontend-config` (ConfigMap):**
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: bi-frontend-config
   data:
     PORT: "3000"
     HOSTNAME: "0.0.0.0"
     NODE_ENV: "production"
     API_INTERNAL_URL: "http://bi-api-service:8000"
   ```
   Contains strictly non-sensitive configuration keys.
2. **`bi-api-secret` (Secret):**
   The frontend Deployment maps only the `API_AUTH_TOKEN` key:
   ```yaml
   env:
     - name: API_AUTH_TOKEN
       valueFrom:
         secretKeyRef:
           name: bi-api-secret
           key: API_AUTH_TOKEN
   ```
3. **Database Boundary Guarantee:**
   `DATABASE_URL` is strictly omitted from the frontend Deployment and ConfigMap. The frontend has zero credentials for and zero connectivity to PostgreSQL.

---

## 5. Resource Bounds & Health Probe Configuration

### Resource Bounds:
- **CPU Requests:** `100m` | **CPU Limits:** `500m`
- **Memory Requests:** `128Mi` | **Memory Limits:** `384Mi`
- Configured specifically for Next.js standalone Node.js runtime memory consumption.

### Probe Contracts:
- **Startup Probe:** `httpGet` `/` on port `http` (3000), `initialDelaySeconds: 3`, `periodSeconds: 3`, `timeoutSeconds: 3`, `failureThreshold: 6` (allows up to 21 seconds for Next.js server initialization).
- **Liveness Probe:** `httpGet` `/` on port `http` (3000), `periodSeconds: 15`, `timeoutSeconds: 3`, `failureThreshold: 3`. Restarts hung Node.js event loops.
- **Readiness Probe:** `httpGet` `/` on port `http` (3000), `periodSeconds: 10`, `timeoutSeconds: 3`, `failureThreshold: 2`. Ensures the container is serving HTML before routing service traffic.

---

## 6. Exact Verification Commands & Test Results

| Test Category | Command | Result |
| :--- | :--- | :--- |
| **Kustomize Render** | `kubectl kustomize deploy/kubernetes` | **Success (Exit code 0)**; Renders all 6 resources (`bi-api-config`, `bi-frontend-config`, `bi-api-service`, `bi-frontend-service`, `bi-api-deployment`, `bi-frontend-deployment`) |
| **Kubernetes Manifest Test Suite** | `/tmp/phase6-env/bin/pytest tests/test_kubernetes_manifests.py -v` | **19 passed in 0.07s** (12 backend + 7 new frontend tests) |
| **Frontend Container Smoke Tests** | `/tmp/phase6-env/bin/pytest tests/test_frontend_container_smoke.py -v` | **4 passed in 1.58s** (root HTTP 200, non-root user UID 1001, secret exclusion, 502 fail-closed) |
| **Backend Container Smoke Tests** | `/tmp/phase6-env/bin/pytest tests/test_container_smoke.py -v` | **8 passed in 2.49s** |
| **Frontend Unit & Proxy Tests** | `docker run --rm -v "$(pwd)/dashboard":/app -w /app node:20 npm test` | **44 passed in 139ms** |
| **Full Python Offline Suite** | `/tmp/phase6-env/bin/pytest -m "not postgres_integration and not docker" -q` | **449 passed in 7.77s** |

---

## 7. Deployment Prerequisites & Live Cluster Scope

### Remaining Prerequisites for Cluster Deployment:
1. **Secret Provisioning:**
   The secret `bi-api-secret` must be created in the target namespace before applying manifests:
   ```bash
   kubectl create secret generic bi-api-secret \
     --from-literal=API_AUTH_TOKEN="$(openssl rand -hex 32)" \
     --from-literal=DATABASE_URL="postgresql://bi_user:bi_password@postgres-host:5432/bi_db"
   ```
2. **Image Availability / Registry:**
   The manifests reference `business-intelligence-api:latest` and `business-intelligence-frontend:latest` with `imagePullPolicy: IfNotPresent`.
   - On local clusters (Minikube / Kind / Docker Desktop K8s), locally built images can be loaded directly (`kind load docker-image ...` or `minikube image load ...`).
   - On remote clusters, images must be pushed to a container registry (e.g., GCR, ECR, Docker Hub) and image names updated or configured via Kustomize `images` transformer.
3. **Live Cluster Verification Scope:**
   Static KRM structure, Kustomize rendering, Docker container runtime execution, and manifest schema constraints were verified. A live remote Kubernetes cluster was not provisioned in this offline phase.

---

## 8. Recommended Next Milestone

**Phase 6K.3: Kustomize Overlay Strategy (Local In-Cluster DB vs. External Production)**
Structure manifests into `base/` (core stateless workloads), `overlays/local` (with lightweight in-cluster PostgreSQL deployment and schema ConfigMap for one-command Minikube/Kind deployment), and `overlays/prod` (for external cloud PostgreSQL).
