import { query } from "./db";
import { ScoringResult } from "@/types";
import { MOCK_BUSINESSES } from "./mockData";

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

export async function getBusinesses(): Promise<ScoringResult[]> {
  try {
    const res = await query(`
      SELECT 
        b.id::text, 
        b.business_name, 
        b.category,
        b.phone,
        b.address,
        b.website as website_url, 
        s.opportunity_score, 
        s.website_quality_score, 
        s.seo_score, 
        s.automation_need_score, 
        s.likely_service_match, 
        s.detected_pain_points,
        b.source_platforms,
        b.google_rating,
        b.review_count,
        b.jd_rating,
        b.jd_reviews_count,
        b.jd_verified,
        b.im_rating,
        b.im_verified,
        b.im_gst_verified,
        COALESCE(b.outreach_status, 'new') AS outreach_status,
        e.extracted_emails,
        t.cms,
        t.analytics_tools,
        t.frontend_framework,
        i.intent_score,
        i.outreach_urgency,
        (SELECT json_agg(dm) FROM (SELECT name, role, confidence FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers
      FROM businesses b
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, opportunity_score, website_quality_score, seo_score, automation_need_score, likely_service_match, detected_pain_points 
        FROM scoring_results 
        ORDER BY business_id, scored_at DESC
      ) s ON b.id = s.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, extracted_emails 
        FROM email_intelligence 
        ORDER BY business_id, extracted_at DESC
      ) e ON b.id = e.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, cms, analytics_tools, frontend_framework 
        FROM tech_stacks 
        ORDER BY business_id, detected_at DESC
      ) t ON b.id = t.business_id
      LEFT JOIN (
        SELECT DISTINCT ON (business_id) business_id, intent_score, outreach_urgency
        FROM intent_profiles
        ORDER BY business_id, evaluated_at DESC
      ) i ON b.id = i.business_id
      ORDER BY s.opportunity_score DESC NULLS LAST, b.id DESC
    `);
    
    return res.rows.map(row => ({
      ...row,
      likely_service_match: typeof row.likely_service_match === 'string' ? JSON.parse(row.likely_service_match) : (row.likely_service_match || []),
      detected_pain_points: normalizePainPoints(row.detected_pain_points),
      source_platforms: typeof row.source_platforms === 'string' ? JSON.parse(row.source_platforms) : (row.source_platforms || []),
      google_rating: row.google_rating !== null ? Number(row.google_rating) : undefined,
      jd_rating: row.jd_rating !== null ? Number(row.jd_rating) : undefined,
      im_rating: row.im_rating !== null ? Number(row.im_rating) : undefined,
      extracted_emails: normalizeEmails(row.extracted_emails),
      analytics_tools: typeof row.analytics_tools === 'string' ? JSON.parse(row.analytics_tools) : (row.analytics_tools || []),
      decision_makers: typeof row.decision_makers === 'string' ? JSON.parse(row.decision_makers) : (row.decision_makers || []),
    }));
  } catch (error) {
    console.error("Database query failed. Falling back to mock data:", error);
    return MOCK_BUSINESSES;
  }
}

