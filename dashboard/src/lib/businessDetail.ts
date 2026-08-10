import { query } from "./db";
import { ScoringResult } from "@/types";
import { normalizeEmails } from "./businesses";
import { MOCK_BUSINESSES } from "./mockData";

/**
 * Fetches a single business with all enrichment data joined.
 * Uses LEFT JOIN throughout so businesses without scoring/reports still load.
 * Falls back to mock data if the database is unreachable.
 */
export async function getBusinessDetail(id: string): Promise<ScoringResult | null> {
  // Critical fix #6: validate id is a safe integer before sending to DB.
  // The URL param is always a string; Postgres would coerce it, but we do it
  // explicitly here to prevent injection vectors and surface bad URLs cleanly.
  const numericId = parseInt(id, 10);
  if (isNaN(numericId) || numericId <= 0) return null;

  try {
    const res = await query(
      `
      SELECT
        b.id::text,
        b.business_name,
        b.website as website_url,
        s.opportunity_score,
        s.website_quality_score,
        s.seo_score,
        s.automation_need_score,
        s.likely_service_match,
        s.detected_pain_points,
        r.overall_opportunity,
        r.website_quality_summary,
        r.seo_summary,
        r.automation_summary,
        r.suggested_services,
        r.outreach_angles,
        r.improvement_recommendations,
        r.raw_text_report,
        COALESCE(b.outreach_status, 'new') AS outreach_status,
        e.extracted_emails,
        t.cms,
        t.frontend_framework,
        t.analytics_tools,
        t.payment_tools,
        t.chat_tools,
        (SELECT json_agg(dm) FROM (SELECT name, role, confidence, source FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers,
        h.overall_health_score,
        h.website_health_score,
        h.review_health_score,
        h.trust_health_score,
        h.conversion_health_score,
        h.conversion_friction_score,
        h.conversion_issues,
        h.trust_signals,
        h.service_recommendations,
        h.opportunity_reasoning,
        c_comp.competitors,
        c_comp.competitor_gap_summary,
        p.recurring_complaints,
        p.recurring_praise,
        p.common_themes,
        p.bottlenecks,
        p.pain_summary
      FROM businesses b
      -- Critical fix #4: LEFT JOIN so unscored businesses still load (not 404).
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, opportunity_score, website_quality_score, seo_score, automation_need_score, likely_service_match, detected_pain_points
        FROM scoring_results
        ORDER BY business_id, scored_at DESC
      ) s ON b.id = s.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, overall_opportunity, website_quality_summary, seo_summary, automation_summary, suggested_services, outreach_angles, improvement_recommendations, raw_text_report
        FROM business_reports
        ORDER BY business_id, generated_at DESC
      ) r ON b.id = r.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, extracted_emails
        FROM email_intelligence
        ORDER BY business_id, extracted_at DESC
      ) e ON b.id = e.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, cms, analytics_tools, frontend_framework, payment_tools, chat_tools
        FROM tech_stacks
        ORDER BY business_id, detected_at DESC
      ) t ON b.id = t.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, overall_health_score, website_health_score, review_health_score, trust_health_score, conversion_health_score, conversion_friction_score, conversion_issues, trust_signals, service_recommendations, opportunity_reasoning
        FROM business_health_profiles
        ORDER BY business_id, evaluated_at DESC
      ) h ON b.id = h.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, competitors, competitor_gap_summary
        FROM competitor_analysis
        ORDER BY business_id, analyzed_at DESC
      ) c_comp ON b.id = c_comp.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, recurring_complaints, recurring_praise, common_themes, bottlenecks, pain_summary
        FROM customer_pain_signals
        ORDER BY business_id, analyzed_at DESC
      ) p ON b.id = p.business_id
      WHERE b.id = $1
      `,
      [numericId]
    );

    if (res.rows.length === 0) return null;

    const row = res.rows[0];
    return transformRow(row);
  } catch (error) {
    console.error(`Database query failed for business ${id}. Falling back to mock data:`, error);
    const mockBiz = MOCK_BUSINESSES.find((b) => b.id === id) || MOCK_BUSINESSES[0];
    return mockBiz;
  }
}

/** Normalizes a raw DB row into a typed ScoringResult. */
function transformRow(row: any): ScoringResult {
  const parseJsonField = (val: any, fallback: any[] = []): any[] => {
    if (val === null || val === undefined) return fallback;
    if (typeof val === "string") {
      try { return JSON.parse(val); } catch { return fallback; }
    }
    return Array.isArray(val) ? val : fallback;
  };

  return {
    id: row.id,
    business_name: row.business_name,
    website_url: row.website_url,
    opportunity_score: row.opportunity_score,
    website_quality_score: row.website_quality_score,
    seo_score: row.seo_score,
    automation_need_score: row.automation_need_score,
    likely_service_match: parseJsonField(row.likely_service_match),
    detected_pain_points: parseJsonField(row.detected_pain_points),
    outreach_status: row.outreach_status,
    extracted_emails: normalizeEmails(row.extracted_emails),
    cms: row.cms,
    frontend_framework: row.frontend_framework,
    analytics_tools: parseJsonField(row.analytics_tools),
    decision_makers: parseJsonField(row.decision_makers),
    overall_health_score: row.overall_health_score !== null ? Number(row.overall_health_score) : undefined,
    website_health_score: row.website_health_score !== null ? Number(row.website_health_score) : undefined,
    review_health_score: row.review_health_score !== null ? Number(row.review_health_score) : undefined,
    trust_health_score: row.trust_health_score !== null ? Number(row.trust_health_score) : undefined,
    conversion_health_score: row.conversion_health_score !== null ? Number(row.conversion_health_score) : undefined,
    conversion_friction_score: row.conversion_friction_score !== null ? Number(row.conversion_friction_score) : undefined,
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
