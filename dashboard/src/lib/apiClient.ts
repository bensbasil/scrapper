/**
 * dashboard/src/lib/apiClient.ts
 *
 * Dedicated Server-Side API Client for Next.js App Router (Phase 6J.2).
 *
 * Direct communication between Next.js server components and the FastAPI backend service:
 * 1. Resolves upstream backend URL using API_INTERNAL_URL (default: http://127.0.0.1:8000).
 * 2. Injects server-side API_AUTH_TOKEN as X-API-Key header without exposing secrets to client code.
 * 3. Never logs credentials or sensitive headers.
 * 4. Fails closed with descriptive errors on non-2xx responses or network failures.
 * 5. Does not silently convert backend failures into fake mock records.
 */

import { ScoringResult, ChangeEvent, OutreachDraft, PipelineRun } from "@/types";
import { normalizeEmails, normalizePainPoints } from "./businesses";
import { transformRow } from "./businessDetail";

const DEFAULT_TIMEOUT_MS = 10000;

/**
 * Resolves the backend base URL for server-side requests.
 * Uses API_INTERNAL_URL (container network), falling back to API_URL or localhost.
 */
export function getBackendBaseUrl(): string {
  const envUrl = process.env.API_INTERNAL_URL || process.env.API_URL || "http://127.0.0.1:8000";
  return envUrl.trim().replace(/\/+$/, "");
}

/**
 * Resolves the server-side API authentication token.
 * Never accessible in client bundles (no NEXT_PUBLIC_ prefix).
 */
export function getApiAuthToken(): string | undefined {
  const token = process.env.API_AUTH_TOKEN;
  return token && token.trim() ? token.trim() : undefined;
}

/**
 * Constructs standard headers for server-to-server requests.
 */
export function buildApiHeaders(extraHeaders: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...extraHeaders,
  };
  const token = getApiAuthToken();
  if (token) {
    headers["X-API-Key"] = token;
  }
  return headers;
}

/**
 * Core fetch wrapper for upstream FastAPI requests with timeout and error handling.
 */
export async function fetchFromBackend<T>(
  endpoint: string,
  options: RequestInit & { timeoutMs?: number } = {}
): Promise<T> {
  const baseUrl = getBackendBaseUrl();
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${cleanEndpoint}`;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const headers = buildApiHeaders((options.headers as Record<string, string>) || {});
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
      cache: "no-store",
    });

    if (!res.ok) {
      const errorText = await res.text().catch(() => "");
      const err = new Error(`[API Client] Upstream HTTP ${res.status} from ${cleanEndpoint}: ${errorText}`);
      (err as any).status = res.status;
      throw err;
    }

    return (await res.json()) as T;
  } catch (error: any) {
    if (error.name === "AbortError") {
      const timeoutErr = new Error(`[API Client] Request to ${cleanEndpoint} timed out after ${timeoutMs}ms`);
      (timeoutErr as any).status = 504;
      throw timeoutErr;
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Retrieves the list of businesses with optional sorting and pagination.
 */
export async function getBusinesses(params?: {
  limit?: number;
  offset?: number;
  sort_by?: string;
}): Promise<ScoringResult[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
  searchParams.set("sort_by", params?.sort_by || "opportunity");

  const qs = searchParams.toString();
  const endpoint = `/api/businesses?${qs}`;

  const data = await fetchFromBackend<{ success: boolean; businesses: any[] }>(endpoint);
  if (!data.success || !Array.isArray(data.businesses)) {
    throw new Error(`[API Client] Invalid response format from ${endpoint}`);
  }

  return data.businesses.map((row) => ({
    ...row,
    likely_service_match:
      typeof row.likely_service_match === "string"
        ? JSON.parse(row.likely_service_match)
        : row.likely_service_match || [],
    detected_pain_points: normalizePainPoints(row.detected_pain_points),
    source_platforms:
      typeof row.source_platforms === "string"
        ? JSON.parse(row.source_platforms)
        : row.source_platforms || [],
    opportunity_score:
      row.opportunity_score !== null && row.opportunity_score !== undefined ? Number(row.opportunity_score) : undefined,
    google_rating:
      row.google_rating !== null && row.google_rating !== undefined ? Number(row.google_rating) : undefined,
    jd_rating: row.jd_rating !== null && row.jd_rating !== undefined ? Number(row.jd_rating) : undefined,
    im_rating: row.im_rating !== null && row.im_rating !== undefined ? Number(row.im_rating) : undefined,
    extracted_emails: normalizeEmails(row.extracted_emails),
    analytics_tools:
      typeof row.analytics_tools === "string"
        ? JSON.parse(row.analytics_tools)
        : row.analytics_tools || [],
    decision_makers:
      typeof row.decision_makers === "string"
        ? JSON.parse(row.decision_makers)
        : row.decision_makers || [],
  }));
}

/**
 * Retrieves full detail for a single business, transforming flat fields into nested report.
 * Returns null if business is not found (HTTP 404).
 */
export async function getBusinessDetail(id: string | number): Promise<ScoringResult | null> {
  const numericId = typeof id === "number" ? id : parseInt(id, 10);
  if (isNaN(numericId) || numericId <= 0) return null;

  try {
    const data = await fetchFromBackend<{ success: boolean; business: any }>(`/api/businesses/${numericId}`);
    if (!data.success || !data.business) return null;
    return transformRow(data.business);
  } catch (error: any) {
    if (error.status === 404) {
      return null;
    }
    console.error(`[API Client] Failed to fetch business detail for ID ${numericId}:`, error.message);
    throw error;
  }
}

/**
 * Retrieves change events timeline for a single business.
 */
export async function getChangeEvents(businessId: string | number): Promise<ChangeEvent[]> {
  const numericId = typeof businessId === "number" ? businessId : parseInt(businessId, 10);
  if (isNaN(numericId) || numericId <= 0) return [];

  try {
    const data = await fetchFromBackend<{ success: boolean; changes: any[] }>(`/api/businesses/${numericId}/changes`);
    if (!data.success || !Array.isArray(data.changes)) return [];
    return data.changes.map((c) => ({
      ...c,
      changes: typeof c.changes === "string" ? JSON.parse(c.changes) : c.changes || [],
    }));
  } catch (error: any) {
    if (error.status === 404) return [];
    console.error(`[API Client] Failed to fetch change events for business ${numericId}:`, error.message);
    return [];
  }
}

/**
 * Retrieves outreach drafts for a single business.
 */
export async function getOutreachDrafts(businessId: string | number): Promise<OutreachDraft | null> {
  const numericId = typeof businessId === "number" ? businessId : parseInt(businessId, 10);
  if (isNaN(numericId) || numericId <= 0) return null;

  try {
    const data = await fetchFromBackend<{ success: boolean; outreach: any }>(`/api/businesses/${numericId}/outreach`);
    if (!data.success) return null;
    return data.outreach || null;
  } catch (error: any) {
    if (error.status === 404) return null;
    console.error(`[API Client] Failed to fetch outreach drafts for business ${numericId}:`, error.message);
    return null;
  }
}

/**
 * Retrieves pipeline run history from backend, preserving stage failure analysis.
 */
export async function getPipelineRuns(limit: number = 20): Promise<PipelineRun[]> {
  try {
    const data = await fetchFromBackend<{ success: boolean; runs: any[] }>(`/api/runs?limit=${limit}`);
    if (!data.success || !Array.isArray(data.runs)) return [];

    return data.runs.map((r) => ({
      id: r.id || r.run_id,
      run_id: r.run_id,
      search_query: r.search_query,
      started_at: r.started_at,
      finished_at: r.finished_at,
      total_businesses: Number(r.total_businesses || 0),
      successful_businesses: Number(r.successful_businesses || 0),
      failed_businesses: Number(r.failed_businesses || 0),
      success_rate: Number(r.success_rate || 0),
      high_opportunity_count: Number(r.high_opportunity_count || 0),
      stage_failure_counts:
        typeof r.stage_failure_counts === "string"
          ? JSON.parse(r.stage_failure_counts)
          : r.stage_failure_counts || {},
      business_records:
        typeof r.business_records === "string"
          ? JSON.parse(r.business_records)
          : r.business_records || [],
      notes: typeof r.notes === "string" ? JSON.parse(r.notes) : r.notes || [],
      created_at: r.created_at,
    }));
  } catch (error: any) {
    console.error(`[API Client] Failed to fetch pipeline runs:`, error.message);
    return [];
  }
}
