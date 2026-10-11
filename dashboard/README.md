# Lead Intelligence Platform — Dashboard

Next.js frontend for the Business Opportunity Intelligence Platform.

---

## 1. Environment Configuration

Copy `.env.example` to `.env.local` for local development:

```bash
cp .env.example .env.local
```

### Environment Variables:

| Variable | Description | Default | Notes |
| :--- | :--- | :--- | :--- |
| `API_INTERNAL_URL` | Upstream FastAPI backend base URL | `http://127.0.0.1:8000` | In Kubernetes, set to `http://bi-api-service:8000`. In Docker Compose, set to `http://api:8000`. |
| `API_AUTH_TOKEN` | Shared secret token for backend authentication | *None* | Must match the backend's `API_AUTH_TOKEN`. Strictly server-side; never exposed to browser bundles. |
| `DATABASE_URL` | PostgreSQL connection string | *None* | Used by server-side query routes. If omitted, falls back safely to mock data for static building. |

---

## 2. Server-Side API Proxy Architecture (Phase 6F.1)

All interactive browser requests to `/api/*` (e.g., `/api/businesses`, `/api/scrape`, `/api/stop`, `/api/status`, `/api/logs`) are handled server-side by the Next.js catch-all route handler:

`src/app/api/[[...path]]/route.ts`

### Security & Operational Guarantees:
1. **Server-Side Token Injection:** The browser client never handles or stores `API_AUTH_TOKEN`. The Next.js server injects the `X-API-Key` header on upstream requests.
2. **Configurable Upstream:** Upstream target address is configured via `API_INTERNAL_URL`, allowing seamless routing across local hosts, Docker networks, and Kubernetes cluster DNS without hardcoded IP addresses.
3. **SSE Streaming Preservation:** Server-Sent Events from `/api/logs` are streamed directly through the proxy without buffering.
4. **Graceful Failure:** If the backend service is offline, the proxy returns a sanitized `502 Bad Gateway` error without leaking internal credentials, host paths, or stack traces.

---

## 3. Development & Testing

### Run Development Server:
```bash
npm run dev
```

### Run Automated Proxy Tests:
```bash
npm test
```

### Build Production Bundle:
```bash
npm run build
```
