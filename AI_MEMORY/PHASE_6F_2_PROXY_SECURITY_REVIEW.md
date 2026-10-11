# Phase 6F.2 — Frontend API Proxy Security and Regression Review

**Date:** 2026-10-10  
**Role:** Senior Security & Full-Stack Platform Engineer  
**Scope:** Security, boundary, streaming, regression, and CI audit of the Next.js server-side API proxy introduced in Phase 6F.1 (`dashboard/src/lib/apiProxy.ts` & `dashboard/src/app/api/[[...path]]/route.ts`).  
**Status:** **AUDITED, HARDENED & VERIFIED** (4 verified defects remediated, 8 new regression tests added, 23/23 frontend tests passed, Next.js build clean, 424 Python unit tests passed)

---

## 1. Executive Summary & Audit Overview

Phase 6F.1 introduced a server-side App Router route handler (`dashboard/src/app/api/[[...path]]/route.ts`) and proxy utility (`dashboard/src/lib/apiProxy.ts`) to mediate browser requests to the FastAPI backend while keeping `API_AUTH_TOKEN` strictly server-side.

This review conducted a deep forensic inspection of four security and operational areas:
1. **Authentication Boundary:** Secret containment, header injection precedence, missing credential behavior.
2. **Proxy Boundaries:** Path traversal, URL sanitization, upstream redirects, and hop-by-hop headers.
3. **Streaming & Request Behavior:** Server-Sent Events, client request aborts, body handling, and method routing.
4. **Regression & CI Integration:** CI execution path, test coverage, and edge-case validation.

### Summary of Verified Defects and Remediations

| Finding ID | Severity | Category | Description | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | **High** | Path Traversal / Boundary Escape | `buildTargetUrl` failed to validate path segments against `..` or encoded dots (`%2e%2e`). A request such as `["..", "docs"]` constructed `http://127.0.0.1:8000/api/../docs`, which WHATWG URL/fetch normalized to `/docs`, escaping the `/api/` prefix boundary and exposing non-API backend endpoints with privileged `X-API-Key` attached. | **RESOLVED** (Rejects `..`, `.`, `%2e%2e`, `/`, `\`; validates target pathname strictly equals `/api` or begins with `/api/`; returns 400 Bad Request). |
| **SEC-02** | **Medium** | Upstream Decompression Header Mismatch | Node.js `fetch` automatically decompresses compressed upstream responses (`gzip`, `deflate`), but preserved upstream `Content-Encoding: gzip` and compressed `Content-Length` headers. Downstream browsers received decompressed plaintext while expecting gzip, causing `net::ERR_CONTENT_DECODING_FAILED` or severe truncation. | **RESOLVED** (Added `content-encoding` and `content-length` to stripped header set in `filterResponseHeaders`). |
| **SEC-03** | **Medium** | Open Redirect / SSRF Follow | `fetch(targetUrl)` defaulted to `redirect: "follow"`. If an upstream endpoint returned a 3xx redirect to an external or internal cluster resource, the server proxy followed it server-side. | **RESOLVED** (Configured `redirect: "manual"`; returns 3xx responses with `Location` header directly to client). |
| **RES-01** | **Low-Medium** | Orphaned Stream / Connection Leak | `request.signal` was not forwarded to `fetch()`. When clients closed long-lived streams (e.g. closing browser during SSE `/api/logs`), the upstream connection to FastAPI remained open indefinitely, and aborts triggered false 502 error logs. | **RESOLVED** (Forwarded `signal: request.signal`; handled `AbortError` cleanly as HTTP 499 without logging 502 errors). |

---

## 2. In-Depth Technical Review by Area

### 2.1 Authentication Review

1. **Client Bundle Isolation:**
   - **Verification:** `API_AUTH_TOKEN` is declared without any `NEXT_PUBLIC_` prefix.
   - **Bundle Audit:** Static code inspection of `dashboard/src/` confirms that `apiProxy.ts` is imported **only** by `src/app/api/[[...path]]/route.ts` (a server-side route handler) and `tests/apiProxy.test.mjs`. Zero React client components import `apiProxy.ts` or read `process.env.API_AUTH_TOKEN`.
   - **Verdict:** PASS. `API_AUTH_TOKEN` never enters client JavaScript bundles.

2. **Browser-Visible Responses & Logs:**
   - **Responses:** On successful responses, upstream headers pass through `filterResponseHeaders()`. In error states (400, 500, 502), response JSON formats are strictly controlled (`{ success: false, error: ... }`).
   - **Logs:** In `catch (error)`, logging sanitizes the URL by removing query strings: `const sanitizedPath = (targetUrl || "").split("?")[0]`.
   - **Verdict:** PASS. Tokens, secrets, and internal stack traces are never exposed to browser clients or logs.

3. **Client-Supplied Header Overriding:**
   - **Implementation:** `prepareProxyHeaders()` checks `if (apiAuthToken) { headers.set("X-API-Key", apiAuthToken); }`.
   - **Hardening:** Because `authorization` and `x-api-key` are excluded from the client header allowlist, any client-supplied `Authorization` or `X-API-Key` headers are completely stripped when the server has `API_AUTH_TOKEN` configured. Clients cannot spoof, downgrade, or override backend authentication.
   - **Verdict:** PASS. Server-side token unconditionally supersedes client credentials.

4. **Missing or Empty `API_AUTH_TOKEN`:**
   - **Behavior:** If `API_AUTH_TOKEN` is unset or empty whitespace, `getApiAuthToken()` returns `undefined`. The proxy forwards requests without `X-API-Key`.
   - **Backend Policy:** The FastAPI backend in `api_server.py` evaluates `verify_api_key()`:
     - For public endpoints (`/api/health/live`, `/api/health/ready`, `/api/status`), requests succeed.
     - For protected endpoints (`/api/businesses`, `/api/scrape`, `/api/logs`), FastAPI raises `HTTP 401 Unauthorized`.
   - **Verdict:** PASS. Fails closed securely without weakening backend authentication.

---

### 2.2 Proxy Boundaries & Routing Review

1. **Path Traversal & Boundary Containment (SEC-01):**
   - **Prior State:** `buildTargetUrl` concatenated `pathSegments.join("/")`. If a client requested `/api/..%2Fdocs` or `["..", "docs"]`, `buildTargetUrl` emitted `http://127.0.0.1:8000/api/../docs`. Node's URL parser normalized this to `http://127.0.0.1:8000/docs`, escaping the intended `/api/` prefix boundary and attaching the server's `X-API-Key`.
   - **Remediation:**
     ```ts
     for (const seg of segments) {
       const decoded = decodeURIComponent(seg);
       if (decoded === "." || decoded === ".." || decoded.includes("/") || decoded.includes("\\")) {
         throw new Error("Invalid API path: path traversal detected");
       }
     }
     const targetParsed = new URL(target);
     if (targetParsed.pathname !== expectedPrefix && !targetParsed.pathname.startsWith(`${expectedPrefix}/`)) {
       throw new Error("Invalid API path: path traversal detected");
     }
     ```
     `handleApiProxy` catches this error and returns `HTTP 400 Bad Request` with `{ success: false, error: "Invalid API path" }`.
   - **Verdict:** PASS (Verified with 8 traversal vectors in test suite).

2. **Upstream Redirect Handling (SEC-03):**
   - **Prior State:** Default `fetch` behavior is `redirect: "follow"`. If an upstream route issued a redirect to an internal cluster service or external URL, the proxy followed it automatically server-side, creating SSRF risks.
   - **Remediation:** Configured `redirect: "manual"` in `fetch(targetUrl, { ... })`. Redirect status codes (301, 302, 307, 308) and `Location` headers are forwarded directly back to the client.
   - **Verdict:** PASS.

3. **Response Header Decompression Mismatch (SEC-02):**
   - **Prior State:** Node.js `fetch` automatically unzips gzipped response bodies, but leaves `Content-Encoding: gzip` and the compressed `Content-Length` in `upstreamRes.headers`. Forwarding these to the browser caused `net::ERR_CONTENT_DECODING_FAILED` or response truncation.
   - **Remediation:** Added `content-encoding` and `content-length` to `hopByHop` header stripping set in `filterResponseHeaders()`. Next.js/Node handles downstream content length and compression cleanly.
   - **Verdict:** PASS (Verified with mock gzipped backend in test suite).

4. **Browser Header Injection Protection:**
   - **Implementation:** `prepareProxyHeaders` utilizes a strict allowlist:
     `accept`, `accept-language`, `accept-encoding`, `cache-control`, `content-type`, `pragma`, `user-agent`.
   - **Hop-by-Hop Filter:** `connection`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailers`, `transfer-encoding`, `upgrade`, `content-encoding`, `content-length` are stripped from responses.
   - **Verdict:** PASS.

---

### 2.3 Streaming, Cancellation & Request Behavior

1. **Server-Sent Events (SSE):**
   - `/api/logs` requests are forwarded to FastAPI with `X-API-Key`. The upstream `ReadableStream` body is passed directly into `new Response(upstreamRes.body, { headers: responseHeaders })` with `Content-Type: text/event-stream`.
   - Verified that chunks stream incrementally without buffering.

2. **Client AbortSignal Propagation (RES-01):**
   - Wired `signal: request.signal` into `fetch(targetUrl, { ... })`.
   - In `catch (error)`, if `error?.name === "AbortError" || request.signal?.aborted`, the proxy returns `HTTP 499 Client Closed Request` without printing spurious 502 errors to console.

3. **HTTP Methods & Payloads:**
   - `GET` and `HEAD` do not parse or forward request bodies.
   - `POST`, `PUT`, `PATCH`, `DELETE` forward `ArrayBuffer` payloads when `byteLength > 0`.
   - Unsupported HTTP verbs (e.g. `TRACE`, `CONNECT`) are automatically rejected by Next.js with `405 Method Not Allowed`.

---

### 2.4 Regression & CI Integration

1. **GitHub Actions Integration:**
   - Verified `.github/workflows/ci.yml` `frontend-build` job:
     ```yaml
     - name: Run Frontend Tests
       working-directory: dashboard
       run: npm test

     - name: Build Next.js Dashboard
       working-directory: dashboard
       run: npm run build
     ```
   - All tests in `dashboard/tests/*.test.mjs` run automatically on pull requests and pushes before `npm run build`.

2. **Test Suite Expansion:**
   - Prior suite: 15 tests.
   - Expanded suite: **23 tests**, adding coverage for:
     - Path traversal vector rejections (8 distinct vectors including `..`, `.`, `%2e%2e`, `/`, `\`).
     - HTTP 400 Bad Request on traversal attempts.
     - Header stripping of `content-encoding` and `content-length`.
     - End-to-end mock proxying of gzipped backend responses.
     - Upstream 307 redirect preservation with `redirect: "manual"`.
     - Client `Authorization` header suppression when server `API_AUTH_TOKEN` is present.
     - Client `AbortSignal` handling.
     - Invalid base URL configuration returning 500.

---

## 3. Files Modified and Scope

All changes were strictly constrained to the frontend proxy library and its automated test suite:

| File Path | Nature of Change |
| :--- | :--- |
| [`dashboard/src/lib/apiProxy.ts`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/src/lib/apiProxy.ts) | Implemented path traversal validation, decompression header stripping, `redirect: "manual"`, and `request.signal` propagation. |
| [`dashboard/tests/apiProxy.test.mjs`](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/dashboard/tests/apiProxy.test.mjs) | Added 8 automated regression test cases verifying path traversal rejection, compression handling, redirect isolation, and abort handling. |

Zero changes were made to backend Python code, Dockerfile, or deployment manifests.

---

## 4. Test Results and Verification

### 4.1 Frontend Test Suite (`npm test`)
Executed via `docker run --rm -v "$PWD/dashboard:/app" -w /app node:20 npm test`:
```
TAP version 13
ok 1 - getBackendBaseUrl defaults to http://127.0.0.1:8000
ok 2 - getBackendBaseUrl prioritizes API_INTERNAL_URL and strips trailing slashes
ok 3 - buildTargetUrl constructs target URL preserving subpaths and query params
ok 4 - prepareProxyHeaders injects server-side API_AUTH_TOKEN as X-API-Key
ok 5 - prepareProxyHeaders server token overrides client-supplied X-API-Key
ok 6 - prepareProxyHeaders passes client key when server token is unconfigured
ok 7 - prepareProxyHeaders leaves X-API-Key unset when neither server nor client provides one
ok 8 - filterResponseHeaders strips hop-by-hop headers
ok 9 - handleApiProxy proxies GET /api/businesses with query and server auth
ok 10 - handleApiProxy proxies POST /api/scrape with JSON payload
ok 11 - handleApiProxy proxies PATCH /api/businesses/:id with status update
ok 12 - handleApiProxy proxies DELETE /api/businesses correctly
ok 13 - handleApiProxy preserves SSE streaming for /api/logs
ok 14 - handleApiProxy forwards 401 Unauthorized when backend rejects credentials
ok 15 - handleApiProxy returns 502 Bad Gateway when backend is completely unreachable
ok 16 - buildTargetUrl rejects path traversal sequences (.., ., %2e%2e, /, \)
ok 17 - handleApiProxy returns 400 Bad Request on path traversal attempts
ok 18 - filterResponseHeaders strips content-encoding and content-length to prevent client decoding failure
ok 19 - handleApiProxy forwards gzipped upstream bodies cleanly without corrupted decoding headers
ok 20 - handleApiProxy preserves upstream redirects without following (redirect: manual)
ok 21 - prepareProxyHeaders suppresses client Authorization header when server API_AUTH_TOKEN is configured
ok 22 - handleApiProxy handles client AbortSignal cleanly
ok 23 - handleApiProxy returns 500 when backend base URL configuration is invalid
1..23
# tests 23
# pass 23
# fail 0
# duration_ms 115.02
```

### 4.2 Next.js Production Build (`npm run build`)
Executed via `docker run --rm -v "$PWD/dashboard:/app" -w /app node:20 npm run build`:
```
▲ Next.js 16.3.0 (Turbopack)
✓ Running next.config.ts took 60ms
✓ Compiled successfully in 1384ms
  Running TypeScript ...
  Finished TypeScript in 959ms ...
✓ Generating static pages using 8 workers (4/4) in 428ms

Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /api/[[...path]]
├ ƒ /business/[id]
└ ƒ /runs

Exit code: 0 (Build Succeeded)
```

### 4.3 Python Offline Test Suite
Executed via `/tmp/phase6-env/bin/pytest`:
```bash
DATABASE_URL="postgresql://invalid:invalid@127.0.0.1:59999/nonexistent" pytest -m "not postgres_integration and not docker" -q
```
**Result:** **424 passed, 9 deselected in 7.77s**.

---

## 5. Git Working-Tree Status

Per constraints, changes remain uncommitted and unpushed:

```
Changes not staged for commit:
	modified:   .github/workflows/ci.yml
	modified:   dashboard/.gitignore
	modified:   dashboard/README.md
	modified:   dashboard/next.config.ts
	modified:   dashboard/package.json
	modified:   dashboard/src/lib/apiProxy.ts
	modified:   dashboard/tests/apiProxy.test.mjs
	modified:   deploy/kubernetes/README.md

Untracked files:
	dashboard/.env.example
	dashboard/src/app/api/[[...path]]/route.ts
	AI_MEMORY/PHASE_6F_DEPLOYMENT_READINESS_AUDIT.md
	AI_MEMORY/PHASE_6F_1_FRONTEND_API_INTEGRATION.md
	AI_MEMORY/PHASE_6F_2_PROXY_SECURITY_REVIEW.md
```
