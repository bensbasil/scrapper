/**
 * dashboard/tests/apiProxy.test.mjs
 *
 * Automated test suite for server-side Next.js API Proxy (Phase 6F.1).
 *
 * Validates:
 * 1. Base URL resolution and trailing-slash normalization.
 * 2. Target URL construction with subpaths and query strings.
 * 3. Server-side API token injection (X-API-Key).
 * 4. Header sanitization and hop-by-hop header removal.
 * 5. Full HTTP proxy lifecycle (GET, POST, PATCH, DELETE) against mock backend.
 * 6. SSE streaming preservation (text/event-stream for /api/logs).
 * 7. Missing server configuration safety (fails closed at backend without secret disclosure).
 * 8. Network failure handling (502 Bad Gateway when upstream is unreachable).
 * 9. Information leakage prevention (zero secret disclosure in responses).
 */

import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import zlib from "node:zlib";
import createJiti from "jiti";

const jiti = createJiti(process.cwd());
/** @type {import('../src/lib/apiProxy')} */
const {
  getBackendBaseUrl,
  getApiAuthToken,
  buildTargetUrl,
  prepareProxyHeaders,
  filterResponseHeaders,
  handleApiProxy,
} = jiti("./src/lib/apiProxy.ts");

// ==============================================================================
// 1. URL & Config Resolution Tests
// ==============================================================================

test("getBackendBaseUrl defaults to http://127.0.0.1:8000", () => {
  const origInternal = process.env.API_INTERNAL_URL;
  const origApi = process.env.API_URL;
  try {
    delete process.env.API_INTERNAL_URL;
    delete process.env.API_URL;
    assert.equal(getBackendBaseUrl(), "http://127.0.0.1:8000");
  } finally {
    if (origInternal) process.env.API_INTERNAL_URL = origInternal;
    if (origApi) process.env.API_URL = origApi;
  }
});

test("getBackendBaseUrl prioritizes API_INTERNAL_URL and strips trailing slashes", () => {
  const orig = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = "http://bi-api-service:8000///";
    assert.equal(getBackendBaseUrl(), "http://bi-api-service:8000");
  } finally {
    if (orig) process.env.API_INTERNAL_URL = orig;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("buildTargetUrl constructs target URL preserving subpaths and query params", () => {
  assert.equal(
    buildTargetUrl(["businesses"], "?limit=20&offset=40", "http://backend:8000"),
    "http://backend:8000/api/businesses?limit=20&offset=40"
  );

  assert.equal(
    buildTargetUrl(["businesses", "42", "outreach"], "", "http://backend:8000/"),
    "http://backend:8000/api/businesses/42/outreach"
  );

  assert.equal(
    buildTargetUrl([], "", "http://backend:8000"),
    "http://backend:8000/api"
  );

  assert.equal(
    buildTargetUrl(undefined, "", "http://backend:8000"),
    "http://backend:8000/api"
  );
});

// ==============================================================================
// 2. Header & Secret Forwarding Tests
// ==============================================================================

test("prepareProxyHeaders injects server-side API_AUTH_TOKEN as X-API-Key", () => {
  const incoming = new Headers({
    "content-type": "application/json",
    accept: "application/json",
  });

  const headers = prepareProxyHeaders(incoming, "server-secret-token-123");
  assert.equal(headers.get("X-API-Key"), "server-secret-token-123");
  assert.equal(headers.get("content-type"), "application/json");
  assert.equal(headers.get("accept"), "application/json");
});

test("prepareProxyHeaders server token overrides client-supplied X-API-Key", () => {
  const incoming = new Headers({
    "x-api-key": "client-fake-key",
  });

  const headers = prepareProxyHeaders(incoming, "canonical-server-key");
  assert.equal(headers.get("X-API-Key"), "canonical-server-key");
});

test("prepareProxyHeaders passes client key when server token is unconfigured", () => {
  const incoming = new Headers({
    "x-api-key": "direct-client-token",
  });

  const headers = prepareProxyHeaders(incoming, undefined);
  assert.equal(headers.get("X-API-Key"), "direct-client-token");
});

test("prepareProxyHeaders leaves X-API-Key unset when neither server nor client provides one", () => {
  const incoming = new Headers({
    "content-type": "application/json",
  });

  const headers = prepareProxyHeaders(incoming, undefined);
  assert.equal(headers.has("X-API-Key"), false);
});

test("filterResponseHeaders strips hop-by-hop headers", () => {
  const upstream = new Headers({
    "content-type": "application/json",
    connection: "keep-alive",
    "transfer-encoding": "chunked",
    "x-custom-backend": "test-backend",
  });

  const filtered = filterResponseHeaders(upstream);
  assert.equal(filtered.get("content-type"), "application/json");
  assert.equal(filtered.get("x-custom-backend"), "test-backend");
  assert.equal(filtered.has("connection"), false);
  assert.equal(filtered.has("transfer-encoding"), false);
});

// ==============================================================================
// 3. Mock Server End-to-End Proxy Lifecycle Tests
// ==============================================================================

/** Helper to create an ephemeral HTTP server for testing. */
function createMockServer(handler) {
  return new Promise((resolve) => {
    const server = http.createServer(handler);
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      resolve({
        server,
        baseUrl: `http://127.0.0.1:${port}`,
        close: () => new Promise((res) => server.close(res)),
      });
    });
  });
}

test("handleApiProxy proxies GET /api/businesses with query and server auth", async () => {
  let receivedAuth = null;
  let receivedUrl = null;

  const mock = await createMockServer((req, res) => {
    receivedAuth = req.headers["x-api-key"];
    receivedUrl = req.url;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ success: true, businesses: [{ id: 1, name: "Test Corp" }] }));
  });

  try {
    const request = new Request("http://frontend/api/businesses?limit=10", {
      method: "GET",
      headers: { accept: "application/json" },
    });

    const response = await handleApiProxy(request, ["businesses"], {
      backendBaseUrl: mock.baseUrl,
      apiAuthToken: "test-auth-secret",
    });

    assert.equal(response.status, 200);
    assert.equal(receivedAuth, "test-auth-secret");
    assert.equal(receivedUrl, "/api/businesses?limit=10");

    const data = await response.json();
    assert.equal(data.success, true);
    assert.equal(data.businesses[0].name, "Test Corp");
  } finally {
    await mock.close();
  }
});

test("handleApiProxy proxies POST /api/scrape with JSON payload", async () => {
  let receivedMethod = null;
  let receivedBody = "";
  let receivedAuth = null;

  const mock = await createMockServer((req, res) => {
    receivedMethod = req.method;
    receivedAuth = req.headers["x-api-key"];
    req.on("data", (chunk) => {
      receivedBody += chunk;
    });
    req.on("end", () => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, message: "Scraper started" }));
    });
  });

  try {
    const payload = JSON.stringify({ category: "dentist", city: "Austin", limit: 5 });
    const request = new Request("http://frontend/api/scrape", {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: payload,
    });

    const response = await handleApiProxy(request, ["scrape"], {
      backendBaseUrl: mock.baseUrl,
      apiAuthToken: "secret-scrape-key",
    });

    assert.equal(response.status, 200);
    assert.equal(receivedMethod, "POST");
    assert.equal(receivedAuth, "secret-scrape-key");
    assert.deepEqual(JSON.parse(receivedBody), { category: "dentist", city: "Austin", limit: 5 });

    const data = await response.json();
    assert.equal(data.success, true);
    assert.equal(data.message, "Scraper started");
  } finally {
    await mock.close();
  }
});

test("handleApiProxy proxies PATCH /api/businesses/:id with status update", async () => {
  let receivedMethod = null;
  let receivedUrl = null;
  let receivedBody = "";

  const mock = await createMockServer((req, res) => {
    receivedMethod = req.method;
    receivedUrl = req.url;
    req.on("data", (chunk) => {
      receivedBody += chunk;
    });
    req.on("end", () => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, id: 99, updated: { outreach_status: "contacted" } }));
    });
  });

  try {
    const payload = JSON.stringify({ outreach_status: "contacted" });
    const request = new Request("http://frontend/api/businesses/99", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: payload,
    });

    const response = await handleApiProxy(request, ["businesses", "99"], {
      backendBaseUrl: mock.baseUrl,
      apiAuthToken: "patch-auth-key",
    });

    assert.equal(response.status, 200);
    assert.equal(receivedMethod, "PATCH");
    assert.equal(receivedUrl, "/api/businesses/99");
    assert.deepEqual(JSON.parse(receivedBody), { outreach_status: "contacted" });

    const data = await response.json();
    assert.equal(data.updated.outreach_status, "contacted");
  } finally {
    await mock.close();
  }
});

test("handleApiProxy proxies DELETE /api/businesses correctly", async () => {
  let receivedMethod = null;

  const mock = await createMockServer((req, res) => {
    receivedMethod = req.method;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ success: true, message: "Cleared" }));
  });

  try {
    const request = new Request("http://frontend/api/businesses", {
      method: "DELETE",
    });

    const response = await handleApiProxy(request, ["businesses"], {
      backendBaseUrl: mock.baseUrl,
      apiAuthToken: "delete-token",
    });

    assert.equal(response.status, 200);
    assert.equal(receivedMethod, "DELETE");
    const data = await response.json();
    assert.equal(data.success, true);
  } finally {
    await mock.close();
  }
});

test("handleApiProxy preserves SSE streaming for /api/logs", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.write("data: [Scraper Info] Initializing browser\n\n");
    res.write("data: [Scraper Output] Found business: Acme\n\n");
    res.end("data: [System] Finished\n\n");
  });

  try {
    const request = new Request("http://frontend/api/logs", {
      method: "GET",
      headers: { accept: "text/event-stream" },
    });

    const response = await handleApiProxy(request, ["logs"], {
      backendBaseUrl: mock.baseUrl,
      apiAuthToken: "sse-token",
    });

    assert.equal(response.status, 200);
    assert.equal(response.headers.get("content-type"), "text/event-stream");

    const text = await response.text();
    assert.match(text, /Initializing browser/);
    assert.match(text, /Found business: Acme/);
    assert.match(text, /Finished/);
  } finally {
    await mock.close();
  }
});

test("handleApiProxy forwards 401 Unauthorized when backend rejects credentials", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "Authentication failed: invalid API key." }));
  });

  try {
    const request = new Request("http://frontend/api/businesses", {
      method: "GET",
    });

    const response = await handleApiProxy(request, ["businesses"], {
      backendBaseUrl: mock.baseUrl,
      apiAuthToken: "bad-token",
    });

    assert.equal(response.status, 401);
    const data = await response.json();
    assert.equal(data.detail, "Authentication failed: invalid API key.");
  } finally {
    await mock.close();
  }
});

test("handleApiProxy returns 502 Bad Gateway when backend is completely unreachable", async () => {
  // Use a port that is not listening (e.g., closed loopback port)
  const deadBaseUrl = "http://127.0.0.1:59998";

  const request = new Request("http://frontend/api/status", {
    method: "GET",
  });

  const response = await handleApiProxy(request, ["status"], {
    backendBaseUrl: deadBaseUrl,
    apiAuthToken: "some-secret-that-must-never-leak",
  });

  assert.equal(response.status, 502);
  const text = await response.text();
  assert.match(text, /Backend service unreachable/);

  // Security check: Assert token was not leaked in error response body
  assert.equal(text.includes("some-secret-that-must-never-leak"), false);
  assert.equal(text.includes("59998"), false);
});

// ==============================================================================
// 4. Security, Boundary & Regression Review Tests (Phase 6F.2)
// ==============================================================================

test("buildTargetUrl rejects path traversal sequences (.., ., %2e%2e, /, \\)", () => {
  const traversalVectors = [
    ["..", "docs"],
    ["..", "openapi.json"],
    ["%2e%2e", "docs"],
    ["..%2Fdocs"],
    ["."],
    ["businesses", "..", "admin"],
    ["businesses/secret"],
    ["businesses\\secret"],
  ];

  for (const vector of traversalVectors) {
    assert.throws(
      () => buildTargetUrl(vector, "", "http://backend:8000"),
      /Invalid API path/,
      `Expected traversal rejection for vector: ${JSON.stringify(vector)}`
    );
  }
});

test("handleApiProxy returns 400 Bad Request on path traversal attempts", async () => {
  const request = new Request("http://frontend/api/../docs", { method: "GET" });
  const response = await handleApiProxy(request, ["..", "docs"], {
    backendBaseUrl: "http://127.0.0.1:8000",
    apiAuthToken: "secret-token",
  });

  assert.equal(response.status, 400);
  const data = await response.json();
  assert.equal(data.success, false);
  assert.equal(data.error, "Invalid API path");
});

test("filterResponseHeaders strips content-encoding and content-length to prevent client decoding failure", () => {
  const upstream = new Headers({
    "content-type": "application/json",
    "content-encoding": "gzip",
    "content-length": "42",
    "x-backend-id": "srv-1",
  });

  const filtered = filterResponseHeaders(upstream);
  assert.equal(filtered.get("content-type"), "application/json");
  assert.equal(filtered.get("x-backend-id"), "srv-1");
  assert.equal(filtered.has("content-encoding"), false);
  assert.equal(filtered.has("content-length"), false);
});

test("handleApiProxy forwards gzipped upstream bodies cleanly without corrupted decoding headers", async () => {
  const mock = await createMockServer((req, res) => {
    const rawPayload = JSON.stringify({ success: true, message: "compressed content" });
    const compressed = zlib.gzipSync(rawPayload);
    res.writeHead(200, {
      "Content-Type": "application/json",
      "Content-Encoding": "gzip",
      "Content-Length": compressed.length,
    });
    res.end(compressed);
  });

  try {
    const request = new Request("http://frontend/api/businesses", { method: "GET" });
    const response = await handleApiProxy(request, ["businesses"], {
      backendBaseUrl: mock.baseUrl,
    });

    assert.equal(response.status, 200);
    // Verified: content-encoding stripped downstream so browser parses decompressed stream correctly
    assert.equal(response.headers.has("content-encoding"), false);
    const data = await response.json();
    assert.equal(data.success, true);
    assert.equal(data.message, "compressed content");
  } finally {
    await mock.close();
  }
});

test("handleApiProxy preserves upstream redirects without following (redirect: manual)", async () => {
  const mock = await createMockServer((req, res) => {
    if (req.url === "/api/legacy") {
      res.writeHead(307, { Location: "/api/businesses" });
      res.end();
    } else {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ target: "reached" }));
    }
  });

  try {
    const request = new Request("http://frontend/api/legacy", { method: "GET" });
    const response = await handleApiProxy(request, ["legacy"], {
      backendBaseUrl: mock.baseUrl,
    });

    // Proxy must return the 307 redirect directly to client rather than following server-side
    assert.equal(response.status, 307);
    assert.equal(response.headers.get("location"), "/api/businesses");
  } finally {
    await mock.close();
  }
});

test("prepareProxyHeaders suppresses client Authorization header when server API_AUTH_TOKEN is configured", () => {
  const incoming = new Headers({
    "authorization": "Bearer client-spoofed-token",
    "x-api-key": "client-spoofed-key",
  });

  const headers = prepareProxyHeaders(incoming, "server-canonical-secret");
  assert.equal(headers.get("X-API-Key"), "server-canonical-secret");
  assert.equal(headers.has("Authorization"), false);
  assert.equal(headers.has("authorization"), false);
});

test("handleApiProxy handles client AbortSignal cleanly", async () => {
  let serverHangResolve;
  const mock = await createMockServer((req, res) => {
    // Keep connection hanging until aborted
    new Promise((resolve) => {
      serverHangResolve = resolve;
    });
  });

  const ac = new AbortController();
  const request = new Request("http://frontend/api/slow", {
    method: "GET",
    signal: ac.signal,
  });

  // Trigger abort shortly after calling
  setTimeout(() => ac.abort(), 20);

  try {
    const response = await handleApiProxy(request, ["slow"], {
      backendBaseUrl: mock.baseUrl,
    });
    assert.equal(response.status, 499);
  } finally {
    if (serverHangResolve) serverHangResolve();
    await mock.close();
  }
});

test("handleApiProxy returns 500 when backend base URL configuration is invalid", async () => {
  const request = new Request("http://frontend/api/businesses", { method: "GET" });
  const response = await handleApiProxy(request, ["businesses"], {
    backendBaseUrl: "://invalid-url-schema",
  });

  assert.equal(response.status, 500);
  const data = await response.json();
  assert.equal(data.error, "Backend service misconfigured");
});

