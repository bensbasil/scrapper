import { query } from "@/lib/db";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ScoringResult } from "@/types";
import StatusSelect from "@/components/StatusSelect";

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

async function getBusinessDetail(id: string): Promise<ScoringResult | null> {
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
    JOIN (
      SELECT DISTINCT ON (business_id) business_id, opportunity_score, website_quality_score, seo_score, automation_need_score, likely_service_match, detected_pain_points 
      FROM scoring_results 
      ORDER BY business_id, scored_at DESC
    ) s ON b.id = s.business_id
    LEFT JOIN business_reports r ON b.id = r.business_id
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
  `, [id]);

  if (res.rows.length === 0) return null;

  const row = res.rows[0];
  
  // Transform DB row into our ScoringResult + Report structure
  return {
    id: row.id,
    business_name: row.business_name,
    website_url: row.website_url,
    opportunity_score: row.opportunity_score,
    website_quality_score: row.website_quality_score,
    seo_score: row.seo_score,
    automation_need_score: row.automation_need_score,
    likely_service_match: typeof row.likely_service_match === 'string' ? JSON.parse(row.likely_service_match) : (row.likely_service_match || []),
    detected_pain_points: typeof row.detected_pain_points === 'string' ? JSON.parse(row.detected_pain_points) : (row.detected_pain_points || []),
    outreach_status: row.outreach_status,
    extracted_emails: normalizeEmails(row.extracted_emails),
    cms: row.cms,
    frontend_framework: row.frontend_framework,
    analytics_tools: typeof row.analytics_tools === 'string' ? JSON.parse(row.analytics_tools) : (row.analytics_tools || []),
    decision_makers: typeof row.decision_makers === 'string' ? JSON.parse(row.decision_makers) : (row.decision_makers || []),
    overall_health_score: row.overall_health_score !== null ? Number(row.overall_health_score) : undefined,
    website_health_score: row.website_health_score !== null ? Number(row.website_health_score) : undefined,
    review_health_score: row.review_health_score !== null ? Number(row.review_health_score) : undefined,
    trust_health_score: row.trust_health_score !== null ? Number(row.trust_health_score) : undefined,
    conversion_health_score: row.conversion_health_score !== null ? Number(row.conversion_health_score) : undefined,
    conversion_friction_score: row.conversion_friction_score !== null ? Number(row.conversion_friction_score) : undefined,
    conversion_issues: typeof row.conversion_issues === 'string' ? JSON.parse(row.conversion_issues) : (row.conversion_issues || []),
    trust_signals: typeof row.trust_signals === 'string' ? JSON.parse(row.trust_signals) : (row.trust_signals || []),
    service_recommendations: typeof row.service_recommendations === 'string' ? JSON.parse(row.service_recommendations) : (row.service_recommendations || []),
    opportunity_reasoning: row.opportunity_reasoning,
    competitors: typeof row.competitors === 'string' ? JSON.parse(row.competitors) : (row.competitors || []),
    competitor_gap_summary: row.competitor_gap_summary,
    recurring_complaints: typeof row.recurring_complaints === 'string' ? JSON.parse(row.recurring_complaints) : (row.recurring_complaints || []),
    recurring_praise: typeof row.recurring_praise === 'string' ? JSON.parse(row.recurring_praise) : (row.recurring_praise || []),
    common_themes: typeof row.common_themes === 'string' ? JSON.parse(row.common_themes) : (row.common_themes || []),
    bottlenecks: typeof row.bottlenecks === 'string' ? JSON.parse(row.bottlenecks) : (row.bottlenecks || []),
    pain_summary: row.pain_summary,
    report: row.overall_opportunity ? {
      business_name: row.business_name,
      overall_opportunity: row.overall_opportunity,
      website_quality_summary: row.website_quality_summary,
      seo_summary: row.seo_summary,
      automation_summary: row.automation_summary,
      suggested_services: typeof row.suggested_services === 'string' ? JSON.parse(row.suggested_services) : (row.suggested_services || []),
      outreach_angles: typeof row.outreach_angles === 'string' ? JSON.parse(row.outreach_angles) : (row.outreach_angles || []),
      improvement_recommendations: typeof row.improvement_recommendations === 'string' ? JSON.parse(row.improvement_recommendations) : (row.improvement_recommendations || []),
      raw_text_report: row.raw_text_report
    } : undefined
  };
}

async function getChangeEvents(businessId: string): Promise<any[]> {
  try {
    const res = await query(`
      SELECT id, changes, previous_snapshot_at, current_snapshot_at, change_summary, detected_at
      FROM change_events
      WHERE business_id = $1
      ORDER BY detected_at DESC
    `, [businessId]);
    
    return res.rows.map(row => ({
      ...row,
      changes: typeof row.changes === 'string' ? JSON.parse(row.changes) : (row.changes || [])
    }));
  } catch (err) {
    console.error("Error fetching change events:", err);
    return [];
  }
}

export default async function BusinessDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const business = await getBusinessDetail(id);
  
  if (!business) return notFound();

  const report = business.report;
  const changes = await getChangeEvents(id);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <Link href="/" className="inline-flex items-center text-sm text-slate-400 hover:text-white transition-colors mb-4">
        <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
        </svg>
        Back to Dashboard
      </Link>

      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-4xl font-extrabold text-white tracking-tight">{business.business_name}</h1>
          <a href={business.website_url || "#"} className="text-blue-400 hover:underline mt-2 inline-block">
            {business.website_url || "No website"}
          </a>
        </div>
        <div className="text-right">
          <div className="text-sm text-slate-400 uppercase tracking-wide font-semibold mb-1">Opportunity Score</div>
          <div className={`inline-flex items-center justify-center px-6 py-2 rounded-xl text-3xl font-black shadow-lg ${business.opportunity_score > 60 ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'}`}>
            {business.opportunity_score} / 100
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
        
        {/* Main Report Area */}
        <div className="lg:col-span-2 space-y-6">
          {/* Health Profile Widget */}
          {business.overall_health_score !== undefined && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-xl">
              <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Business Health Profile
              </h2>

              <div className="flex flex-col md:flex-row items-center gap-8">
                {/* SVG Gauge */}
                <div className="relative flex items-center justify-center w-36 h-36 shrink-0">
                  <div className={`absolute inset-0 rounded-full blur-md opacity-25 ${
                    (business.overall_health_score || 0) >= 75 ? 'bg-emerald-500/10' : (business.overall_health_score || 0) >= 50 ? 'bg-amber-500/10' : 'bg-rose-500/10'
                  }`}></div>
                  <svg className="w-full h-full transform -rotate-90">
                    <circle
                      cx="72"
                      cy="72"
                      r="60"
                      className="stroke-slate-800"
                      strokeWidth="10"
                      fill="transparent"
                    />
                    <circle
                      cx="72"
                      cy="72"
                      r="60"
                      className={`${
                        (business.overall_health_score || 0) >= 75 ? 'stroke-emerald-500' : (business.overall_health_score || 0) >= 50 ? 'stroke-amber-500' : 'stroke-rose-500'
                      }`}
                      strokeWidth="10"
                      fill="transparent"
                      strokeDasharray={2 * Math.PI * 60}
                      strokeDashoffset={2 * Math.PI * 60 * (1 - (business.overall_health_score || 0) / 100)}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="absolute flex flex-col items-center justify-center">
                    <span className="text-3xl font-black text-white">{Math.round(business.overall_health_score || 0)}%</span>
                    <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Health Index</span>
                  </div>
                </div>

                {/* Progress bars */}
                <div className="flex-1 w-full space-y-4">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Health Sub-Scores</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <div className="flex justify-between text-xs font-semibold text-slate-300 mb-1">
                        <span>Website Architecture</span>
                        <span>{business.website_health_score || 0}%</span>
                      </div>
                      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${business.website_health_score || 0}%` }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold text-slate-300 mb-1">
                        <span>Conversion & Lead Flow</span>
                        <span>{business.conversion_health_score || 0}%</span>
                      </div>
                      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full bg-violet-500 rounded-full" style={{ width: `${business.conversion_health_score || 0}%` }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold text-slate-300 mb-1">
                        <span>Review Sentiment</span>
                        <span>{business.review_health_score || 0}%</span>
                      </div>
                      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${business.review_health_score || 0}%` }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold text-slate-300 mb-1">
                        <span>Trust & Credibility</span>
                        <span>{business.trust_health_score || 0}%</span>
                      </div>
                      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full bg-amber-500 rounded-full" style={{ width: `${business.trust_health_score || 0}%` }}></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Conversion issues and trust signals */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-6 border-t border-slate-800 mt-6">
                <div>
                  <h4 className="text-xs font-bold text-rose-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Friction Points ({business.conversion_issues?.length || 0})
                  </h4>
                  {business.conversion_issues && business.conversion_issues.length > 0 ? (
                    <div className="space-y-2">
                      {business.conversion_issues.map((issue, idx) => (
                        <div key={idx} className="flex gap-2 text-sm text-slate-300 bg-rose-500/5 border border-rose-500/10 rounded-xl p-2.5">
                          <span className="text-rose-500 font-bold">⚠️</span>
                          <span>{issue}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 italic">No major conversion friction issues detected.</p>
                  )}
                </div>

                <div>
                  <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                    Trust Signals ({business.trust_signals?.length || 0})
                  </h4>
                  {business.trust_signals && business.trust_signals.length > 0 ? (
                    <div className="space-y-2">
                      {business.trust_signals.map((signal, idx) => (
                        <div key={idx} className="flex gap-2 text-sm text-slate-300 bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-2.5">
                          <span className="text-emerald-500 font-bold">✓</span>
                          <span>{signal}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 italic">No verified trust signals detected on landing page.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Suggested Services & Pitch Reasoning */}
          {((business.service_recommendations && business.service_recommendations.length > 0) || business.opportunity_reasoning) && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                Outreach Service Mapping
              </h2>

              {business.opportunity_reasoning && (
                <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-5">
                  <h3 className="text-xs font-bold text-blue-400 uppercase tracking-wider mb-2">Opportunity Reasoning Narrative</h3>
                  <p className="text-slate-300 leading-relaxed text-sm">{business.opportunity_reasoning}</p>
                </div>
              )}

              {business.service_recommendations && business.service_recommendations.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {business.service_recommendations.map((rec: any, idx: number) => (
                    <div key={idx} className="bg-white/5 border border-white/5 rounded-xl p-4 flex flex-col justify-between">
                      <div>
                        <h4 className="font-bold text-white text-sm mb-1.5 flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                          {rec.service_name}
                        </h4>
                        <p className="text-slate-400 text-xs leading-relaxed">{rec.impact_explanation}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Executive Summary */}
          {report ? (
            <>
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
                <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                  <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Executive Summary
                </h2>
                <p className="text-slate-300 leading-relaxed text-lg">{report.overall_opportunity}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                  <h3 className="font-semibold text-white mb-3">Website Quality</h3>
                  <p className="text-slate-400 text-sm">{report.website_quality_summary}</p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                  <h3 className="font-semibold text-white mb-3">SEO & Visibility</h3>
                  <p className="text-slate-400 text-sm">{report.seo_summary}</p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 md:col-span-2">
                  <h3 className="font-semibold text-white mb-3">Conversion & Automation</h3>
                  <p className="text-slate-400 text-sm">{report.automation_summary}</p>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center">
              <h2 className="text-xl font-bold text-white mb-2">No Detailed Report Generated</h2>
              <p className="text-slate-400 text-sm">Please trigger an audit for this website to view execution summaries.</p>
            </div>
          )}

          {/* Voice of the Customer (Pains & Praise) */}
          {(business.pain_summary || (business.recurring_complaints && business.recurring_complaints.length > 0) || (business.recurring_praise && business.recurring_praise.length > 0)) && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a1.994 1.994 0 01-1.414-.586m0 0L11 14h4a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2v4l.586-.586z" />
                </svg>
                Customer Review Miner & Pain Signals
              </h2>

              {business.pain_summary && (
                <p className="text-slate-300 leading-relaxed text-sm">{business.pain_summary}</p>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Praises */}
                <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-5 space-y-3">
                  <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Recurring Praise
                  </h3>
                  {business.recurring_praise && business.recurring_praise.length > 0 ? (
                    <ul className="space-y-2">
                      {business.recurring_praise.map((praise, idx) => (
                        <li key={idx} className="text-xs text-slate-300 flex items-start gap-2">
                          <span className="text-emerald-500 font-bold mt-0.5">✓</span>
                          <span>{praise}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-slate-500 italic">No significant positive feedback patterns mined.</p>
                  )}
                </div>

                {/* Complaints */}
                <div className="bg-rose-500/5 border border-rose-500/10 rounded-xl p-5 space-y-3">
                  <h3 className="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Recurring Complaints & Pain Points
                  </h3>
                  {business.recurring_complaints && business.recurring_complaints.length > 0 ? (
                    <ul className="space-y-2">
                      {business.recurring_complaints.map((complaint, idx) => (
                        <li key={idx} className="text-xs text-slate-300 flex items-start gap-2">
                          <span className="text-rose-500 font-bold mt-0.5">⚠️</span>
                          <span>{complaint}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-slate-500 italic">No critical complaint patterns mined.</p>
                  )}
                </div>
              </div>

              {((business.common_themes && business.common_themes.length > 0) || (business.bottlenecks && business.bottlenecks.length > 0)) && (
                <div className="flex flex-wrap gap-4 pt-2">
                  {business.common_themes && business.common_themes.length > 0 && (
                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Key Themes</span>
                      <div className="flex flex-wrap gap-1.5">
                        {business.common_themes.map((theme, idx) => (
                          <span key={idx} className="text-[10px] px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 font-semibold">
                            {theme}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {business.bottlenecks && business.bottlenecks.length > 0 && (
                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Service Bottlenecks</span>
                      <div className="flex flex-wrap gap-1.5">
                        {business.bottlenecks.map((bottleneck, idx) => (
                          <span key={idx} className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-semibold">
                            {bottleneck}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Competitor Gap Analysis */}
          {((business.competitors && business.competitors.length > 0) || business.competitor_gap_summary) && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                Local Competitor Gap Analysis
              </h2>

              {business.competitor_gap_summary && (
                <p className="text-slate-300 leading-relaxed text-sm">{business.competitor_gap_summary}</p>
              )}

              {business.competitors && business.competitors.length > 0 ? (
                <div className="overflow-x-auto rounded-xl border border-slate-800">
                  <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
                    <thead className="bg-white/5 text-slate-300 font-semibold text-xs uppercase tracking-wider">
                      <tr>
                        <th className="px-4 py-3">Competitor Name</th>
                        <th className="px-4 py-3">Website</th>
                        <th className="px-4 py-3">Rating</th>
                        <th className="px-4 py-3 text-right">Opp Score Gap</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800 text-slate-300">
                      {business.competitors.map((comp: any, idx: number) => {
                        const gap = comp.score_gap || 0;
                        const gapText = gap > 0 ? `+${gap}` : `${gap}`;
                        const gapColor = gap > 0 ? 'text-emerald-400' : gap < 0 ? 'text-rose-400' : 'text-slate-400';
                        return (
                          <tr key={idx} className="hover:bg-white/5 transition-colors">
                            <td className="px-4 py-3.5 font-medium text-white">{comp.name}</td>
                            <td className="px-4 py-3.5">
                              {comp.website && comp.website !== 'None' ? (
                                <a href={comp.website} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline truncate max-w-[180px] inline-block">
                                  {comp.website.replace(/^https?:\/\/(www\.)?/, '')}
                                </a>
                              ) : (
                                <span className="text-slate-500 italic text-xs">No website</span>
                              )}
                            </td>
                            <td className="px-4 py-3.5">
                              {comp.rating ? (
                                <span className="flex items-center gap-1">
                                  <span className="text-amber-400">★</span>
                                  {comp.rating}
                                </span>
                              ) : (
                                <span className="text-slate-500 italic text-xs">N/A</span>
                              )}
                            </td>
                            <td className={`px-4 py-3.5 text-right font-black ${gapColor}`}>
                              {gapText}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic">No local competitors recorded in the database yet.</p>
              )}
            </div>
          )}

          {/* Crawl Change History Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="font-bold text-white mb-4 uppercase tracking-wider text-sm flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Crawl Change History
            </h3>
            {changes.length === 0 ? (
              <p className="text-xs text-slate-500">No changes detected yet across crawls.</p>
            ) : (
              <div className="space-y-4">
                {changes.map((event) => (
                  <div key={event.id} className="border-l border-slate-700 pl-3 py-1">
                    <div className="text-[10px] text-slate-400">
                      {new Date(event.detected_at).toLocaleString()}
                    </div>
                    <div className="text-xs font-semibold text-slate-200 mt-1">
                      {event.change_summary}
                    </div>
                    <div className="mt-2 space-y-1">
                      {event.changes.map((c: any, idx: number) => (
                        <div key={idx} className="text-[10px] text-slate-400 bg-white/5 px-1.5 py-0.5 rounded flex justify-between">
                          <span className="font-medium text-slate-300">{c.field}</span>
                          <span>{c.before === null ? 'None' : String(c.before)} → {c.after === null ? 'None' : String(c.after)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar Area */}
        <div className="space-y-6">
          {/* Outreach Status Selector & Target Emails */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6">
            <StatusSelect businessId={business.id} initialStatus={business.outreach_status || 'new'} />
            
            <div className="border-t border-slate-800 pt-4">
              <h4 className="font-bold text-white text-xs uppercase tracking-wider mb-3">Enriched Emails</h4>
              {business.extracted_emails && business.extracted_emails.length > 0 ? (
                <div className="space-y-2">
                  {business.extracted_emails.map((email: string, idx: number) => (
                    <div key={idx} className="flex justify-between items-center bg-white/5 px-3 py-2 rounded-xl border border-white/5">
                      <span className="text-sm text-slate-300 truncate max-w-[200px]" title={email}>{email}</span>
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20">Regex Verified</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">No emails extracted from site crawl.</p>
              )}
            </div>
          </div>

          {/* Decision Makers Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="font-bold text-white mb-4 uppercase tracking-wider text-sm flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Decision Makers
            </h3>
            {business.decision_makers && business.decision_makers.length > 0 ? (
              <div className="space-y-3">
                {business.decision_makers.map((dm: any, idx: number) => (
                  <div key={idx} className="bg-white/5 border border-white/5 rounded-xl p-3 space-y-1">
                    <div className="font-bold text-white text-sm">{dm.name}</div>
                    <div className="text-xs text-slate-400">{dm.role || "Executive / Decision Maker"}</div>
                    <div className="flex justify-between items-center text-[10px] text-slate-500 pt-1 border-t border-white/5">
                      <span>Source: <strong className="text-slate-400">{dm.source || "Web"}</strong></span>
                      <span className="px-1 py-0.5 rounded bg-blue-500/10 text-blue-400 font-semibold">{Math.round((dm.confidence || 0.5) * 100)}% Conf</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No decision makers identified yet.</p>
            )}
          </div>

          {/* Tech Stack Details Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="font-bold text-white mb-4 uppercase tracking-wider text-sm flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              Detected Tech Stack
            </h3>
            <div className="space-y-4">
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">CMS / Core Platform</span>
                <span className="px-2.5 py-1 rounded bg-white/5 text-slate-200 border border-white/5 text-xs font-semibold inline-block">
                  {business.cms || "Custom / Jamstack"}
                </span>
              </div>
              {business.frontend_framework && (
                <div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Frontend Framework</span>
                  <span className="px-2.5 py-1 rounded bg-white/5 text-slate-200 border border-white/5 text-xs font-semibold inline-block">
                    {business.frontend_framework}
                  </span>
                </div>
              )}
              {business.analytics_tools && business.analytics_tools.length > 0 && (
                <div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">Analytics & Marketing</span>
                  <div className="flex flex-wrap gap-1.5">
                    {business.analytics_tools.map((tool: string) => (
                      <span key={tool} className="text-[10px] px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 font-semibold">
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {!business.cms && !business.frontend_framework && (!business.analytics_tools || business.analytics_tools.length === 0) && (
                <p className="text-xs text-slate-500">No core tech stack details detected.</p>
              )}
            </div>
          </div>

          {report && (
            <>
              <div className="bg-gradient-to-b from-blue-900/40 to-slate-900 border border-blue-500/20 rounded-2xl p-6">
                <h3 className="font-bold text-white mb-4 uppercase tracking-wider text-sm">Suggested Services</h3>
                <div className="flex flex-wrap gap-2">
                  {report.suggested_services.map(s => (
                    <span key={s} className="px-3 py-1.5 rounded-lg bg-blue-500/20 text-blue-300 text-sm font-medium border border-blue-500/30">
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                <h3 className="font-bold text-white mb-4 uppercase tracking-wider text-sm">Pitch Angles</h3>
                <ul className="space-y-3">
                  {report.outreach_angles.map((angle, i) => (
                    <li key={i} className="flex gap-3 text-sm text-slate-300">
                      <span className="text-blue-500 mt-0.5">•</span>
                      <span>{angle}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                <h3 className="font-bold text-white mb-4 uppercase tracking-wider text-sm">Action Items</h3>
                <ul className="space-y-3">
                  {report.improvement_recommendations.map((rec, i) => (
                    <li key={i} className="flex gap-3 text-sm text-slate-300">
                      <span className="text-green-500 mt-0.5">✓</span>
                      <span>{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>
        
      </div>
    </div>
  );
}
