# Local Multi-Container Deployment (Docker Compose)

Reproducible local multi-container environment for the **Business Opportunity Intelligence Platform** (Phase 6I-A).

---

## 1. Architecture Overview

The Compose deployment orchestrates three interconnected services on a dedicated bridge network (`bi-network`):

```
+-----------------------------------------------------------------------------------------+
| DOCKER NETWORK: bi-network                                                              |
|                                                                                         |
|  +--------------------+         +--------------------+         +---------------------+  |
|  | postgres           | <------ | backend            | <------ | frontend            |  |
|  | (PostgreSQL 15)    |         | (FastAPI API)      |         | (Next.js Dashboard) |  |
|  | Port: 5432         |         | Port: 8000         |         | Port: 3000          |  |
|  | Volume: data       |         | Health: /health    |         | Proxy: /api/*       |  |
|  +--------------------+         +--------------------+         +---------------------+  |
|            ^                                                              |             |
|            +--------------------------------------------------------------+             |
|                                 (Direct SSR read query)                                 |
+-----------------------------------------------------------------------------------------+
                                             |                              |
                                  Host Port: 8000                Host Port: 3000
```

### Services:
1. **`postgres` (`bi-postgres`):** Official PostgreSQL 15 Alpine database with health checks and persistent volume storage. Initial schema is automatically initialized on clean startup via `database/schema.sql`.
2. **`backend` (`bi-backend`):** FastAPI application container running as non-root user `appuser`. Connects to `postgres:5432` and exposes REST API endpoints on port 8000.
3. **`frontend` (`bi-frontend`):** Next.js 16 standalone application container running as non-root user `nextjs`. Proxies interactive API traffic to `http://backend:8000` via its server-side route handler, and executes initial SSR page renders directly against PostgreSQL.

---

## 2. Quick Start

### 2.1 Configuration (Optional)
The deployment includes built-in development defaults (`bi_user`, `bi_password`, `bi_db`). To customize variables, copy `.env.example`:

```bash
cp deploy/.env.example deploy/.env
```

### 2.2 Start the Entire Stack
Run from the repository root:

```bash
docker compose -f deploy/docker-compose.yaml up -d
```

Compose starts the database first, waits for the `pg_isready` health check to pass, builds and starts the backend, waits for backend liveness, and finally starts the frontend dashboard.

### 2.3 Verify Container Status
Check health and port bindings:

```bash
docker compose -f deploy/docker-compose.yaml ps
```

All three services should display `healthy`:
```
NAME          IMAGE                                COMMAND                  SERVICE    CREATED          STATUS                    PORTS
bi-backend    business-intelligence-api:local      "uvicorn api_server:…"   backend    10 seconds ago   Up 9 seconds (healthy)    0.0.0.0:8000->8000/tcp
bi-frontend   business-intelligence-frontend:local "docker-entrypoint.s…"   frontend   10 seconds ago   Up 8 seconds (healthy)    0.0.0.0:3000->3000/tcp
bi-postgres   postgres:15-alpine                   "docker-entrypoint.s…"   postgres   12 seconds ago   Up 11 seconds (healthy)   0.0.0.0:5432->5432/tcp
```

### 2.4 Access the Application
- **Frontend Dashboard:** [http://localhost:3000](http://localhost:3000)
- **Backend API Status:** [http://localhost:8000/api/status](http://localhost:8000/api/status)
- **Backend Health Check:** [http://localhost:8000/api/health/live](http://localhost:8000/api/health/live)

---

## 3. Operations & Smoke Testing

### 3.1 Smoke Testing the Running Stack
Test the complete integration path from host curl commands:

```bash
# 1. Verify Frontend serves HTTP 200
curl -I http://localhost:3000/

# 2. Verify Frontend Server Proxy routes to Backend status
curl -s http://localhost:3000/api/status

# 3. Verify Frontend Proxy injects server authentication into Backend businesses API
curl -s http://localhost:3000/api/businesses

# 4. Verify Backend reports database is connected and ready
curl -s http://localhost:8000/api/health/ready
```

### 3.2 Viewing Logs
```bash
# View all logs in real-time
docker compose -f deploy/docker-compose.yaml logs -f

# View backend API logs
docker compose -f deploy/docker-compose.yaml logs -f backend

# View frontend logs
docker compose -f deploy/docker-compose.yaml logs -f frontend
```

---

## 4. Database Persistence & Lifecycle

### 4.1 Persistent Volume (`bi_postgres_data`)
Application data, scraped businesses, logs, and pipeline runs are stored in the named Docker volume `postgres_data` (`bi_postgres_data`).

### 4.2 Standard Shutdown (Preserves Data)
To stop the application while **preserving all database records and scraped leads**:

```bash
docker compose -f deploy/docker-compose.yaml down
```

Starting the stack again with `up -d` reconnects to the existing volume with all data intact.

### 4.3 Database Schema Initialization Rule
> [!IMPORTANT]
> PostgreSQL entrypoint initialization scripts (`/docker-entrypoint-initdb.d/01_schema.sql`) run **ONLY when initializing an empty database**.
> If data already exists in the volume, PostgreSQL skips initialization scripts to prevent overwriting data.

### 4.4 Resetting the Database to Clean Slate
If you want to completely wipe local data and re-run `database/schema.sql` from scratch, pass the `-v` / `--volumes` flag during teardown:

```bash
docker compose -f deploy/docker-compose.yaml down -v
```

Then start the stack again:

```bash
docker compose -f deploy/docker-compose.yaml up -d
```

---

## 5. Security & Secret Containment

1. **No Baked Secrets:** Neither `deploy/docker-compose.yaml` nor the Dockerfiles bake credentials into image layers.
2. **Localhost Isolation:** The frontend proxy routes to `http://backend:8000` inside the private bridge network. The client browser only connects to port 3000.
3. **Server-Side Token Injection:** The client browser never receives `API_AUTH_TOKEN`. The Next.js server injects `X-API-Key` into upstream requests to the backend.
4. **Non-Root Execution:** Both backend (`appuser`, UID 1000) and frontend (`nextjs`, UID 1001) run under dedicated unprivileged users.
