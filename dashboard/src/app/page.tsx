import { query } from "@/lib/db";
import BusinessDashboard from "@/components/BusinessDashboard";
import { ScoringResult } from "@/types";

export const dynamic = 'force-dynamic';

function normalizeEmails(emailsRaw: any): string[] {
  if (!emailsRaw) return [];
  try {
    const list = typeof emailsRaw === 'string' ? JSON.parse(emailsRaw) : emailsRaw;
    if (!Array.isArray(list)) return [];
    return list
      .map((item: any) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && item.email) return item.email;
        return null;
      })
      .filter(Boolean) as string[];
  } catch (e) {
    return [];
  }
}

async function getBusinesses(): Promise<ScoringResult[]> {
  const res = await query(`
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
      (SELECT json_agg(dm) FROM (SELECT name, role, confidence FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers
    FROM businesses b
    JOIN (
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
    ORDER BY s.opportunity_score DESC
  `);
  
  return res.rows.map(row => ({
    ...row,
    likely_service_match: typeof row.likely_service_match === 'string' ? JSON.parse(row.likely_service_match) : (row.likely_service_match || []),
    detected_pain_points: typeof row.detected_pain_points === 'string' ? JSON.parse(row.detected_pain_points) : (row.detected_pain_points || []),
    source_platforms: typeof row.source_platforms === 'string' ? JSON.parse(row.source_platforms) : (row.source_platforms || []),
    google_rating: row.google_rating !== null ? Number(row.google_rating) : undefined,
    jd_rating: row.jd_rating !== null ? Number(row.jd_rating) : undefined,
    im_rating: row.im_rating !== null ? Number(row.im_rating) : undefined,
    extracted_emails: normalizeEmails(row.extracted_emails),
    analytics_tools: typeof row.analytics_tools === 'string' ? JSON.parse(row.analytics_tools) : (row.analytics_tools || []),
    decision_makers: typeof row.decision_makers === 'string' ? JSON.parse(row.decision_makers) : (row.decision_makers || []),
  }));
}

export default async function Home() {
  const businesses = await getBusinesses();
  
  const totalLeads = businesses.length;
  const newLeads = businesses.filter(b => b.outreach_status === 'new').length;
  const contactedLeads = businesses.filter(b => b.outreach_status === 'contacted' || b.outreach_status === 'followed_up').length;
  const avgOppScore = totalLeads > 0 
    ? (businesses.reduce((acc, b) => acc + b.opportunity_score, 0) / totalLeads).toFixed(1)
    : "0.0";

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white">Prospects</h2>
          <p className="text-slate-400 mt-1">Real-time intelligence from your scraper.</p>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Total Leads</p>
          <p className="text-3xl font-bold text-blue-400">{totalLeads}</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">New Leads</p>
          <p className="text-3xl font-bold text-yellow-400">{newLeads}</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Contacted Leads</p>
          <p className="text-3xl font-bold text-emerald-400">{contactedLeads}</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Average Opp Score</p>
          <p className="text-3xl font-bold text-white">{avgOppScore}</p>
        </div>
      </div>

      <BusinessDashboard initialBusinesses={businesses} />
    </div>
  );
}
