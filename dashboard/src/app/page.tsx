import { query } from "@/lib/db";
import BusinessDashboard from "@/components/BusinessDashboard";
import { ScoringResult } from "@/types";

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
      s.detected_pain_points
    FROM businesses b
    JOIN scoring_results s ON b.id = s.business_id
    ORDER BY s.opportunity_score DESC
  `);
  
  return res.rows.map(row => ({
    ...row,
    likely_service_match: typeof row.likely_service_match === 'string' ? JSON.parse(row.likely_service_match) : (row.likely_service_match || []),
    detected_pain_points: typeof row.detected_pain_points === 'string' ? JSON.parse(row.detected_pain_points) : (row.detected_pain_points || []),
  }));
}

export default async function Home() {
  const businesses = await getBusinesses();
  
  const totalLeads = businesses.length;
  const avgOppScore = totalLeads > 0 
    ? (businesses.reduce((acc, b) => acc + b.opportunity_score, 0) / totalLeads).toFixed(1)
    : "0.0";
  const missingWebsites = businesses.filter(b => !b.website_url).length;

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white">Prospects</h2>
          <p className="text-slate-400 mt-1">Real-time intelligence from your scraper.</p>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Average Opp Score</p>
          <p className="text-3xl font-bold text-white">{avgOppScore}</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Missing Websites</p>
          <p className="text-3xl font-bold text-red-400">{missingWebsites}</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Total Leads</p>
          <p className="text-3xl font-bold text-blue-400">{totalLeads}</p>
        </div>
      </div>

      <BusinessDashboard initialBusinesses={businesses} />
    </div>
  );
}
