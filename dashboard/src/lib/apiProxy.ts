/**
 * dashboard/src/lib/apiProxy.ts
 *
 * Server-side API Proxy for Next.js App Router (Phase 6F.1).
 *
 * Responsibilities:
 * 1. Forwards client requests to the backend FastAPI service via API_INTERNAL_URL.
 * 2. Injects server-side API_AUTH_TOKEN as X-API-Key header without exposing secrets to the browser.
 * 3. Handles all HTTP methods (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS).
 * 4. Supports streaming responses, specifically Server-Sent Events (SSE) for /api/logs.
 * 5. Fails closed safely when backend is unreachable (502 Bad Gateway) or unconfigured.
 * 6. Never exposes internal tokens, connection strings, or stack traces to client responses.
 */

export interface ProxyConfig {
  backendBaseUrl: string;
  apiAuthToken?: string;
}

/**
 * Resolves the backend base URL from environment variables.
 * Defaults to http://127.0.0.1:8000 for local development.
 */
export function getBackendBaseUrl(): string {
  const envUrl = process.env.API_INTERNAL_URL || process.env.API_URL || "http://127.0.0.1:8000";
  return envUrl.trim().replace(/\/+$/, "");
}

/**
 * Resolves the server-side API authentication token.
 * Never accessible client-side (no NEXT_PUBLIC_ prefix).
 */
export function getApiAuthToken(): string | undefined {
  const token = process.env.API_AUTH_TOKEN;
  return token && token.trim() ? token.trim() : undefined;
}

/**
 * Constructs the upstream URL preserving subpaths and query parameters.
 * Validates path segments against directory traversal attacks (.., ., encoded dots).
 * Ensures the resolved target URL pathname never escapes the /api prefix boundary.
 */
export function buildTargetUrl(
  subpath: string | string[] | undefined,
  searchParams: string = "",
  baseUrl: string = getBackendBaseUrl()
): string {
  const cleanBase = baseUrl.trim().replace(/\/+$/, "");
  let baseParsed: URL;
  try {
    baseParsed = new URL(cleanBase);
  } catch {
    throw new Error(`Invalid base URL: ${baseUrl}`);
  }

  const basePath = baseParsed.pathname === "/" ? "" : baseParsed.pathname.replace(/\/+$/, "");
  const expectedPrefix = `${basePath}/api`;

  const rawSegments = Array.isArray(subpath)
    ? subpath
    : (subpath || "").split("/").filter(Boolean);
  const segments = rawSegments.filter(Boolean);

  for (const seg of segments) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(seg);
    } catch {
      throw new Error("Invalid API path: malformed encoding");
    }
    if (
      decoded === "." ||
      decoded === ".." ||
      decoded.includes("/") ||
      decoded.includes("\\")
    ) {
      throw new Error("Invalid API path: path traversal detected");
    }
  }

  const fullPath = segments.length > 0 ? `${expectedPrefix}/${segments.join("/")}` : expectedPrefix;
  const search = searchParams ? (searchParams.startsWith("?") ? searchParams : `?${searchParams}`) : "";
  const target = `${baseParsed.origin}${fullPath}${search}`;

  const targetParsed = new URL(target);
  if (
    targetParsed.pathname !== expectedPrefix &&
    !targetParsed.pathname.startsWith(`${expectedPrefix}/`)
  ) {
    throw new Error("Invalid API path: path traversal detected");
  }

  return target;
}

/**
 * Prepares request headers for upstream forwarding:
 * - Forwards safe client request headers.
 * - Filters out hop-by-hop headers.
 * - Injects server-side X-API-Key token if configured.
 * - If server token is not configured, allows client-supplied token (if any).
 */
export function prepareProxyHeaders(
  incomingHeaders: Headers,
  apiAuthToken: string | undefined = getApiAuthToken()
): Headers {
  const headers = new Headers();

  // Forward common safe headers
  const allowlist = [
    "accept",
    "accept-language",
    "accept-encoding",
    "cache-control",
    "content-type",
    "pragma",
    "user-agent",
  ];

  for (const name of allowlist) {
    const val = incomingHeaders.get(name);
    if (val) {
      headers.set(name, val);
    }
  }

  // Security: Inject server-side API key if configured.
  // When configured, client-supplied X-API-Key and Authorization are strictly overridden/omitted.
  if (apiAuthToken) {
    headers.set("X-API-Key", apiAuthToken);
  } else {
    // If server has no token configured, pass client-supplied credentials (if any)
    const clientKey = incomingHeaders.get("x-api-key");
    if (clientKey) {
      headers.set("X-API-Key", clientKey);
    }
    const clientAuth = incomingHeaders.get("authorization");
    if (clientAuth) {
      headers.set("Authorization", clientAuth);
    }
  }

  return headers;
}

/**
 * Filters out hop-by-hop headers and decompression headers from upstream response.
 * Note: Node fetch automatically decompresses upstream bodies (gzip, deflate),
 * so content-encoding and content-length must be stripped to prevent
 * net::ERR_CONTENT_DECODING_FAILED or response truncation in client browsers.
 */
export function filterResponseHeaders(upstreamHeaders: Headers): Headers {
  const headers = new Headers();
  const hopByHop = new Set([
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
  ]);

  upstreamHeaders.forEach((val, key) => {
    if (!hopByHop.has(key.toLowerCase())) {
      headers.set(key, val);
    }
  });

  return headers;
}

/**
 * Main proxy execution function.
 */
export async function handleApiProxy(
  request: Request,
  pathSegments?: string[],
  configOverrides?: Partial<ProxyConfig>
): Promise<Response> {
  const backendBase = configOverrides?.backendBaseUrl || getBackendBaseUrl();
  const token = configOverrides?.apiAuthToken !== undefined ? configOverrides.apiAuthToken : getApiAuthToken();

  let targetUrl: string;
  try {
    const reqUrl = new URL(request.url);
    targetUrl = buildTargetUrl(pathSegments, reqUrl.search, backendBase);
  } catch (error: any) {
    if (error?.message?.includes("Invalid API path")) {
      return Response.json(
        { success: false, error: "Invalid API path" },
        { status: 400 }
      );
    }
    return Response.json(
      { success: false, error: "Backend service misconfigured" },
      { status: 500 }
    );
  }

  const upstreamHeaders = prepareProxyHeaders(request.headers, token);

  // Extract body for methods that support bodies
  let body: ArrayBuffer | undefined = undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      const rawBody = await request.arrayBuffer();
      if (rawBody.byteLength > 0) {
        body = rawBody;
      }
    } catch {
      return Response.json(
        { error: "Invalid request body" },
        { status: 400 }
      );
    }
  }

  try {
    const upstreamRes = await fetch(targetUrl, {
      method: request.method,
      headers: upstreamHeaders,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    });

    const responseHeaders = filterResponseHeaders(upstreamRes.headers);

    return new Response(upstreamRes.body, {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: responseHeaders,
    });
  } catch (error: any) {
    if (error?.name === "AbortError" || request.signal?.aborted) {
      return new Response(null, { status: 499, statusText: "Client Closed Request" });
    }

    // Sanitize log output — do not leak query secrets or tokens
    const sanitizedPath = (targetUrl || "").split("?")[0];
    console.error(`[API Proxy] Upstream request failed for ${request.method} ${sanitizedPath}: ${error?.message || "Connection failed"}`);

    return Response.json(
      {
        success: false,
        error: "Backend service unreachable",
      },
      { status: 502 }
    );
  }
}
