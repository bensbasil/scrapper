/**
 * dashboard/src/lib/businesses.ts
 *
 * Business data retrieval and normalization utilities.
 * Migrated in Phase 6J.2 from direct PostgreSQL queries to FastAPI backend.
 */

import { ScoringResult } from "@/types";
import { fetchFromBackend } from "./apiClient";

export function normalizeEmails(emailsRaw: any): string[] {
  if (!emailsRaw) return [];
  try {
    const list = typeof emailsRaw === 'string' ? JSON.parse(emailsRaw) : emailsRaw;
    if (!Array.isArray(list)) return [];
    return list
      .map((item: any) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          if (typeof item.email === 'string') return item.email;
          if (typeof item.address === 'string') return item.address;
          if (typeof item.value === 'string') return item.value;
          if (item.email && typeof item.email === 'object' && item.email.email) return String(item.email.email);
        }
        return null;
      })
      .filter((e): e is string => typeof e === 'string' && e.length > 0);
  } catch (e) {
    return [];
  }
}

export function normalizePainPoints(pointsRaw: any): string[] {
  if (!pointsRaw) return [];
  try {
    const list = typeof pointsRaw === 'string' ? JSON.parse(pointsRaw) : pointsRaw;
    if (!Array.isArray(list)) return [];
    return list
      .map((item: any) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          return item.validation_error || item.issue || item.error || JSON.stringify(item);
        }
        return String(item);
      })
      .filter(Boolean) as string[];
  } catch (e) {
    return [];
  }
}

export async function getBusinesses(params?: {
  limit?: number;
  offset?: number;
  sort_by?: string;
}): Promise<ScoringResult[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
  // Default to opportunity sorting to preserve dashboard ordering
  searchParams.set("sort_by", params?.sort_by || "opportunity");

  const qs = searchParams.toString();
  const endpoint = `/api/businesses?${qs}`;

  try {
    const data = await fetchFromBackend<{ success: boolean; businesses: any[] }>(endpoint);
    if (!data.success || !Array.isArray(data.businesses)) {
      console.error(`[Businesses] Upstream API returned unexpected format from ${endpoint}`);
      return [];
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
  } catch (error: any) {
    console.error(`[Businesses] Backend API fetch failed for ${endpoint}:`, error.message);
    return [];
  }
}
