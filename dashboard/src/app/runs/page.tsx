import { query } from "@/lib/db";
import Link from "next/link";

export const dynamic = 'force-dynamic';

interface PipelineRun {
  id: string;
  run_id: string;
  search_query: string;
  started_at: Date;
  finished_at: Date | null;
  total_businesses: number;
  successful_businesses: number;
  failed_businesses: number;
  success_rate: number;
  high_opportunity_count: number;
  stage_failure_counts: Record<string, number> | string;
  business_records: any[] | string;
  notes: string[] | string;
}

async function getPipelineRuns(): Promise<PipelineRun[]> {
  try {
    const res = await query(`
      SELECT 
        id::text,
        run_id,
        search_query,
        started_at,
        finished_at,
        total_businesses,
        successful_businesses,
        failed_businesses,
        success_rate,
        high_opportunity_count,
        stage_failure_counts,
        business_records,
        notes
      FROM pipeline_runs
      ORDER BY started_at DESC
    `);
    
    return res.rows.map(row => ({
      ...row,
      stage_failure_counts: typeof row.stage_failure_counts === 'string' ? JSON.parse(row.stage_failure_counts) : (row.stage_failure_counts || {}),
      business_records: typeof row.business_records === 'string' ? JSON.parse(row.business_records) : (row.business_records || []),
      notes: typeof row.notes === 'string' ? JSON.parse(row.notes) : (row.notes || []),
    }));
  } catch (err) {
    console.error("Error fetching pipeline runs:", err);
    return [];
  }
}

export default async function RunsHistoryPage() {
  const runs = await getPipelineRuns();
  
  const totalRuns = runs.length;
  const avgSuccessRate = totalRuns > 0 
    ? (runs.reduce((acc, r) => acc + Number(r.success_rate), 0) / totalRuns).toFixed(1)
    : "0.0";
  const totalHighOppLeads = runs.reduce((acc, r) => acc + r.high_opportunity_count, 0);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white">Pipeline Run History</h2>
          <p className="text-slate-400 mt-1">Operational health metrics and stage failure analysis.</p>
        </div>
        <Link href="/" className="bg-slate-900 hover:bg-slate-800 text-white border border-slate-700 px-4 py-2 rounded-xl text-sm font-bold transition-all">
          Back to Dashboard
        </Link>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Total Pipeline Runs</p>
          <p className="text-3xl font-bold text-white">{totalRuns}</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Average Success Rate</p>
          <p className="text-3xl font-bold text-green-400">{avgSuccessRate}%</p>
        </div>
        <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg">
          <p className="text-sm text-slate-400 font-medium mb-1">Total High Opportunity Leads</p>
          <p className="text-3xl font-bold text-blue-400">{totalHighOppLeads}</p>
        </div>
      </div>

      {/* Runs Table */}
      {runs.length === 0 ? (
        <div className="text-center py-20 bg-white/5 border border-dashed border-white/10 rounded-2xl">
          <p className="text-slate-400">No pipeline runs recorded yet. Start a scrape on the dashboard!</p>
        </div>
      ) : (
        <div className="bg-slate-900/50 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-sm">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-white/10 bg-white/5">
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Run ID & Start Time</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Query Source</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest text-center">Success Rate</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest text-center">High Opp</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest text-center">Businesses</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Stage Failures / Errors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {runs.map((run) => {
                const startedTime = new Date(run.started_at).toLocaleString();
                const finishedTime = run.finished_at ? new Date(run.finished_at).toLocaleTimeString() : "Running...";
                
                const failures = run.stage_failure_counts as Record<string, number>;
                const failureKeys = Object.keys(failures).filter(k => failures[k] > 0);

                return (
                  <tr key={run.id} className="hover:bg-white/5 transition-colors">
                    <td className="p-4">
                      <div className="font-bold text-white">{run.run_id}</div>
                      <div className="text-xs text-slate-400 mt-1">{startedTime}</div>
                    </td>
                    <td className="p-4 font-mono text-sm text-slate-300">
                      {run.search_query}
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-block px-3 py-1 rounded-full text-xs font-black ${run.success_rate >= 80 ? 'bg-green-500/20 text-green-400' : run.success_rate >= 55 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}`}>
                        {run.success_rate}%
                      </span>
                    </td>
                    <td className="p-4 text-center text-blue-400 font-bold">
                      {run.high_opportunity_count}
                    </td>
                    <td className="p-4 text-center text-slate-300 text-sm">
                      {run.successful_businesses} / {run.total_businesses}
                    </td>
                    <td className="p-4">
                      {failureKeys.length === 0 ? (
                        <span className="text-xs text-green-400 font-semibold bg-green-500/10 border border-green-500/20 px-2 py-1 rounded-md">All Stages Clean</span>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {failureKeys.map(stage => (
                            <span key={stage} className="text-[10px] text-red-400 font-bold bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                              {stage}: {failures[stage]}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
