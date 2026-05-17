import { query } from "@/lib/db";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ScoringResult, BusinessReport } from "@/types";

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
      r.raw_text_report
    FROM businesses b
    JOIN scoring_results s ON b.id = s.business_id
    LEFT JOIN business_reports r ON b.id = r.business_id
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

export default async function BusinessDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const business = await getBusinessDetail(id);
  
  if (!business) return notFound();

  const report = business.report;

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

      {report && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
          
          {/* Main Report Area */}
          <div className="lg:col-span-2 space-y-6">
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
          </div>

          {/* Sidebar Area */}
          <div className="space-y-6">
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
          </div>
          
        </div>
      )}
    </div>
  );
}
