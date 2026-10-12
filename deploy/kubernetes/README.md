# Kubernetes Deployment Guide: Business Opportunity Intelligence Platform

This directory contains declarative Kubernetes manifests for the Business Opportunity Intelligence Platform, organized into a standard Kustomize **Base + Overlays** architecture.

---

## Architecture & Layout Overview

```text
deploy/kubernetes/
├── README.md                          # Platform operations and deployment guide
├── kustomization.yaml                 # Root backward-compatible alias (points to base/)
├── base/                              # Shared application workloads (core 6 resources)
│   ├── kustomization.yaml
│   ├── deployment.yaml                # FastAPI backend Deployment (bi-api-deployment)
│   ├── service.yaml                   # FastAPI backend Service (bi-api-service, port 8000)
│   ├── configmap.yaml                 # FastAPI backend ConfigMap (bi-api-config)
│   ├── frontend-deployment.yaml      # Next.js standalone Deployment (bi-frontend-deployment)
│   ├── frontend-service.yaml         # Next.js frontend Service (bi-frontend-service, port 3000)
│   ├── frontend-configmap.yaml       # Next.js frontend ConfigMap (bi-frontend-config)
│   └── secret.example.yaml           # Operator template for bi-api-secret
└── overlays/
    ├── local/                         # Local cluster target (Kind, Minikube, Docker Desktop)
    │   ├── kustomization.yaml         # In-cluster PostgreSQL + Dev Secret + Schema mount
    │   ├── postgres-deployment.yaml   # PostgreSQL 15 single-replica Deployment
    │   ├── postgres-service.yaml      # PostgreSQL ClusterIP Service (bi-postgres-service, port 5432)
    │   ├── postgres-pvc.yaml          # PersistentVolumeClaim (1Gi ReadWriteOnce)
    │   └── 01_schema.sql              # Schema initialization SQL sourced from database/schema.sql
    └── prod/                          # Production cluster target (EKS, GKE, AKS, Bare-Metal)
        ├── kustomization.yaml         # Production overlay (Managed external DB, no in-cluster DB)
        └── patches/
            └── resource-tuning.yaml   # Minimal production resource tuning patch
```

### Layer Responsibilities:

| Layer | Path | Responsibility & Workloads |
| :--- | :--- | :--- |
| **Root (Compat)** | `deploy/kubernetes/` | Backward-compatibility forwarder to `base/`. Guarantees existing scripts/CI running `kubectl kustomize deploy/kubernetes` continue to build the 6 core resources. |
| **Base** | `deploy/kubernetes/base/` | Declarative definitions for the core FastAPI backend and Next.js frontend workloads. Strictly excludes database workloads and plaintext credentials. |
| **Local Overlay** | `deploy/kubernetes/overlays/local/` | Developer/demo harness. Provisions an in-cluster single-replica `postgres:15-alpine` deployment with a 1Gi PVC, auto-seeds `01_schema.sql` via ConfigMap on first boot, and generates development `bi-api-secret`. |
| **Production Overlay**| `deploy/kubernetes/overlays/prod/` | Hardened production target. Relies strictly on externally managed PostgreSQL (AWS RDS, GCP Cloud SQL) and external cluster secret management. Strictly omits in-cluster DB and PVCs. |

---

## Component Inventory

- **`bi-api-config` (ConfigMap):** Non-sensitive backend configuration (`PORT: "8000"`, `PYTHONUNBUFFERED`, `ALLOWED_ORIGINS`, pool parameters).
- **`bi-api-service` (Service):** Internal `ClusterIP` proxying traffic to backend pods on port 8000.
- **`bi-api-deployment` (Deployment):** Single-replica backend API (`replicas: 1`, `Recreate` strategy, non-root `appuser` UID 1000).
- **`bi-frontend-config` (ConfigMap):** Non-sensitive frontend configuration (`PORT: "3000"`, `API_INTERNAL_URL="http://bi-api-service:8000"`).
- **`bi-frontend-service` (Service):** Internal `ClusterIP` proxying traffic to frontend pods on port 3000.
- **`bi-frontend-deployment` (Deployment):** Stateless Next.js standalone frontend (`replicas: 1`, `RollingUpdate` strategy, non-root `nextjs` UID 1001, zero database access).
- **`bi-postgres-service` (Local only):** Internal `ClusterIP` proxying port 5432 to local PostgreSQL.
- **`bi-postgres-deployment` (Local only):** `postgres:15-alpine` pod running non-root (UID 70).
- **`bi-postgres-pvc` (Local only):** Local `ReadWriteOnce` persistent disk storage.

---

## Single-Replica Safety & Strategy Rationale

### 1. Why the Backend Uses One Replica (`replicas: 1`):
The backend utilizes process-local in-memory state for:
- Agent task results (`/api/agent/tasks/{task_id}`).
- Subprocess scraper management (`running_process`, `/api/scrape`, `/api/stop`, `/api/status`).
- SSE log broadcasting (`/api/logs`).
- Bounded telemetry sink ring buffers.
Running multiple uncoordinated backend replicas behind a round-robin Service causes split-brain task lookup 404s and duplicate simultaneous scraping runs.

### 2. Why the Backend Strategy is `Recreate`:
A standard `RollingUpdate` with `maxSurge: 1` spins up a replacement pod while the old pod is still terminating. This surge window violates single-replica mutual exclusion, causing split-brain scraping and duplicate database connections. The `Recreate` strategy terminates the existing pod first, allowing clean process termination before launching the replacement pod. (Downtime window: ~5–15s).

---

## Local / Demo Cluster Quickstart (Kind / Minikube)

### 1. Prerequisites:
- `kubectl` v1.24+
- Local Kubernetes cluster (e.g., Kind or Minikube)
- Docker daemon (for building container images)

### 2. Build and Load Images into Cluster:
```bash
# Build backend container image
docker build -t business-intelligence-api:latest .

# Build frontend container image
docker build -t business-intelligence-frontend:latest dashboard

# For Kind clusters, load the local images into the cluster nodes:
kind load docker-image business-intelligence-api:latest
kind load docker-image business-intelligence-frontend:latest

# For Minikube clusters:
# minikube image load business-intelligence-api:latest
# minikube image load business-intelligence-frontend:latest
```

### 3. Render and Apply Local Overlay:
```bash
# Render the local overlay to inspect KRM manifests
kubectl kustomize deploy/kubernetes/overlays/local

# Apply the complete 3-tier platform (App + Frontend + Postgres)
kubectl apply -k deploy/kubernetes/overlays/local
```

### 4. Verify Rollout & Readiness:
```bash
# Wait for PostgreSQL to become ready
kubectl rollout status deployment/bi-postgres-deployment

# Wait for Backend API rollout
kubectl rollout status deployment/bi-api-deployment

# Wait for Frontend Dashboard rollout
kubectl rollout status deployment/bi-frontend-deployment

# Inspect all workloads
kubectl get pods,services,pvc -o wide
```

### 5. Access the Platform via Port-Forwarding:
```bash
# Forward Frontend Dashboard (Port 3000)
kubectl port-forward svc/bi-frontend-service 3000:3000

# In a separate terminal, forward Backend API (Port 8000)
kubectl port-forward svc/bi-api-service 8000:8000

# Open Dashboard in your browser:
# http://localhost:3000
```

---

## Local Database Lifecycle & Data Reset

### 1. Schema Initialization Semantics:
- The local overlay packages `database/schema.sql` into the `bi-postgres-schema` ConfigMap.
- Mounted read-only at `/docker-entrypoint-initdb.d/`.
- PostgreSQL executes this script **strictly once**, during initial cluster boot when `/var/lib/postgresql/data/pgdata` is empty.
- Pod restarts detect an existing database directory and safely bypass initialization.

> [!IMPORTANT]
> **Schema Migrations:** Modifying `01_schema.sql` or `database/schema.sql` will **NOT** automatically update an existing, populated database. To apply schema changes locally, follow the data reset procedure below.

### 2. How to Reset Local Database Data Safely:
To wipe all test entities, scrapers, and task records and return to a pristine state:
```bash
# Delete the local PersistentVolumeClaim
kubectl delete pvc bi-postgres-pvc

# Restart the PostgreSQL deployment to trigger re-creation with clean schema
kubectl rollout restart deployment/bi-postgres-deployment
```

### 3. Limitations of Local In-Cluster PostgreSQL:
- **No Production HA:** Lacks automated WAL archiving, streaming replication, read replicas, or automated backups.
- **RWO Bound:** Storage is bound to a single cluster node (`ReadWriteOnce`).
- Intended strictly for local development, integration testing, and offline demonstration.

---

## Hardened Production Deployment

### 1. Secret Provisioning (Out-of-Band):
Production credentials must **NEVER** be committed into git or placed in ConfigMaps. In production, provision `bi-api-secret` prior to deployment:

```bash
# Generate a cryptographically secure auth token
API_AUTH_TOKEN=$(openssl rand -hex 32)

# Provision secret targeting external managed PostgreSQL (RDS, Cloud SQL)
kubectl create secret generic bi-api-secret \
  --from-literal=API_AUTH_TOKEN="${API_AUTH_TOKEN}" \
  --from-literal=DATABASE_URL="postgresql://prod_user:SECURE_PASSWORD@managed-db.internal:5432/prod_db" \
  --from-literal=GEMINI_API_KEY="AIzaSyYourProductionApiKey"
```
*(Or configure the External Secrets Operator / SealedSecrets to sync from your cloud secret vault).*

### 2. Configure Production Container Images:
In your CI/CD release pipeline, configure the tagged production container image repositories:
```bash
cd deploy/kubernetes/overlays/prod
kustomize edit set image business-intelligence-api=registry.example.com/org/bi-api:v1.2.0
kustomize edit set image business-intelligence-frontend=registry.example.com/org/bi-frontend:v1.2.0
```

### 3. Apply Production Overlay:
```bash
# Render to inspect
kubectl kustomize deploy/kubernetes/overlays/prod

# Apply to cluster
kubectl apply -k deploy/kubernetes/overlays/prod
```

---

## Diagnostic & Inspection Commands

```bash
# View backend live logs
kubectl logs -l app.kubernetes.io/name=business-intelligence-api -c api -f

# View frontend live logs
kubectl logs -l app.kubernetes.io/name=business-intelligence-frontend -c frontend -f

# View local postgres logs
kubectl logs -l app.kubernetes.io/name=business-intelligence-postgres -c postgres -f

# Check probe events or failures
kubectl describe pod -l app.kubernetes.io/name=business-intelligence-api
kubectl describe pod -l app.kubernetes.io/name=business-intelligence-frontend
```

---

## Verification & Manifest Testing

All manifests across root, base, local, and production overlays are continuously verified via automated tests:

```bash
# Run complete manifest validation test suite (30 assertions)
pytest tests/test_kubernetes_manifests.py -v

# Run full Python offline test suite
pytest -m "not postgres_integration and not docker" -q
```
*(Note: Automated tests validate KRM schema conformance, security profiles, probe contracts, and Kustomize generation. Live cluster rollouts require an active running cluster).*
