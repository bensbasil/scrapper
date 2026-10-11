/**
 * dashboard/src/lib/businessDetail.ts
 *
 * Detailed business enrichment and report normalization.
 * Migrated in Phase 6J.2 from direct PostgreSQL queries to FastAPI backend.
 */

import { ScoringResult } from "@/types";
import { normalizeEmails, normalizePainPoints } from "./businesses";
import { fetchFromBackend } from "./apiClient";

/**
 * Normalizes a raw business payload into a typed ScoringResult,
 * preserving the nested report structure expected by the detail page.
 */
export function transformRow(row: any): ScoringResult {
  const parseJsonField = (val: any, fallback: any[] = []): any[] => {
    if (val === null || val === undefined) return fallback;
    if (typeof val === "string") {
      try { return JSON.parse(val); } catch { return fallback; }
    }
    return Array.isArray(val) ? val : fallback;
  };

  return {
    id: String(row.id),
    business_name: row.business_name,
    website_url: row.website_url,
    opportunity_score: row.opportunity_score,
    website_quality_score: row.website_quality_score,
    seo_score: row.seo_score,
    automation_need_score: row.automation_need_score,
    likely_service_match: parseJsonField(row.likely_service_match),
    detected_pain_points: normalizePainPoints(row.detected_pain_points),
    outreach_status: row.outreach_status,

    extracted_emails: normalizeEmails(row.extracted_emails),
    cms: row.cms,
    frontend_framework: row.frontend_framework,
    analytics_tools: parseJsonField(row.analytics_tools),
    decision_makers: parseJsonField(row.decision_makers),
    overall_health_score: row.overall_health_score !== null && row.overall_health_score !== undefined ? Number(row.overall_health_score) : undefined,
    website_health_score: row.website_health_score !== null && row.website_health_score !== undefined ? Number(row.website_health_score) : undefined,
    review_health_score: row.review_health_score !== null && row.review_health_score !== undefined ? Number(row.review_health_score) : undefined,
    trust_health_score: row.trust_health_score !== null && row.trust_health_score !== undefined ? Number(row.trust_health_score) : undefined,
    conversion_health_score: row.conversion_health_score !== null && row.conversion_health_score !== undefined ? Number(row.conversion_health_score) : undefined,
    conversion_friction_score: row.conversion_friction_score !== null && row.conversion_friction_score !== undefined ? Number(row.conversion_friction_score) : undefined,
    conversion_issues: parseJsonField(row.conversion_issues),
    trust_signals: parseJsonField(row.trust_signals),
    service_recommendations: parseJsonField(row.service_recommendations),
    opportunity_reasoning: row.opportunity_reasoning,
    competitors: parseJsonField(row.competitors),
    competitor_gap_summary: row.competitor_gap_summary,
    recurring_complaints: parseJsonField(row.recurring_complaints),
    recurring_praise: parseJsonField(row.recurring_praise),
    common_themes: parseJsonField(row.common_themes),
    bottlenecks: parseJsonField(row.bottlenecks),
    pain_summary: row.pain_summary,
    report: row.overall_opportunity
      ? {
          business_name: row.business_name,
          overall_opportunity: row.overall_opportunity,
          website_quality_summary: row.website_quality_summary,
          seo_summary: row.seo_summary,
          automation_summary: row.automation_summary,
          suggested_services: parseJsonField(row.suggested_services),
          outreach_angles: parseJsonField(row.outreach_angles),
          improvement_recommendations: parseJsonField(row.improvement_recommendations),
          raw_text_report: row.raw_text_report,
        }
      : undefined,
  };
}

/**
 * Fetches a single business with all enrichment data joined from FastAPI.
 * Returns null if the business does not exist (404) or on invalid ID.
 */
export async function getBusinessDetail(id: string): Promise<ScoringResult | null> {
  const numericId = parseInt(id, 10);
  if (isNaN(numericId) || numericId <= 0) return null;

  try {
    const data = await fetchFromBackend<{ success: boolean; business: any }>(`/api/businesses/${numericId}`);
    if (!data.success || !data.business) return null;
    return transformRow(data.business);
  } catch (error: any) {
    if (error.status === 404) {
      return null;
    }
    console.error(`[BusinessDetail] Error fetching business detail for ID ${numericId}:`, error.message);
    return null;
  }
}
