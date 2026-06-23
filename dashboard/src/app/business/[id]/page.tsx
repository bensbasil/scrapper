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
      (SELECT json_agg(dm) FROM (SELECT name, role, confidence, source FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers
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
