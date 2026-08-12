"use client";
import { ScoringResult } from "@/types";
import Link from "next/link";

function getScoreColor(score: number | undefined | null) {
  if (score === undefined || score === null) return "bg-slate-800 text-slate-400 animate-pulse";
  if (score >= 70) return "bg-red-500 text-white"; // High opportunity (bad website)
  if (score >= 40) return "bg-yellow-400 text-slate-900"; // Moderate
  return "bg-green-500 text-white"; // Low opportunity (good website)
}

const statusStyles: Record<string, { label: string; style: string }> = {
  new: { label: "New", style: "bg-sky-500/20 text-sky-300 border-sky-500/30" },
  contacted: { label: "Contacted", style: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30" },
  followed_up: { label: "Followed Up", style: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  closed: { label: "Closed", style: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
};

export default function BusinessCard({ business }: { business: ScoringResult }) {
  const status = business.outreach_status || "new";
  const statusConfig = statusStyles[status] || statusStyles.new;

  return (
    <Link href={`/business/${business.id}`} className="block transition-transform hover:-translate-y-1">
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300 relative overflow-hidden group">

        {/* Decorative gradient blob */}
        <div className="absolute -right-10 -top-10 w-32 h-32 bg-blue-500/20 rounded-full blur-3xl group-hover:bg-blue-400/30 transition-all"></div>

        <div className="flex justify-between items-start mb-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <h3 className="text-xl font-bold text-white leading-tight">{business.business_name}</h3>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold border uppercase tracking-wider ${statusConfig.style}`}>
                {statusConfig.label}
              </span>
            </div>
            {business.website_url ? (
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  if (business.website_url) {
                    window.open(business.website_url, "_blank");
                  }
                }}
                className="text-blue-400 text-sm hover:underline cursor-pointer"
              >
                {business.website_url.replace(/^https?:\/\//, '')}
              </div>
            ) : (
              <span className="text-red-400 text-sm font-medium">No Website Detected</span>
            )}

            {/* Source platforms badges */}
            {business.source_platforms && business.source_platforms.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {business.source_platforms.map(source => {
                  const colors: Record<string, string> = {
                    google_maps: "bg-blue-500/10 text-blue-400 border-blue-500/20",
                    justdial: "bg-orange-500/10 text-orange-400 border-orange-500/20",
                    indiamart: "bg-teal-500/10 text-teal-400 border-teal-500/20"
                  };
                  const label: Record<string, string> = {
                    google_maps: "Google Maps",
                    justdial: "JustDial",
                    indiamart: "IndiaMart"
                  };
                  return (
                    <span 
                      key={source} 
                      className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border ${colors[source] || "bg-slate-500/10 text-slate-400 border-slate-500/20"}`}
                    >
                      {label[source] || source}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
          <div className={`flex flex-col items-center justify-center w-16 h-16 rounded-xl ${getScoreColor(business.opportunity_score)} shadow-lg text-center`}>
            <span className="text-[10px] font-bold opacity-80 uppercase tracking-wider">
              {business.opportunity_score === undefined || business.opportunity_score === null ? "Status" : "Opp"}
            </span>
            <span className="text-xs font-black px-1">
              {business.opportunity_score === undefined || business.opportunity_score === null ? "PENDING" : business.opportunity_score}
            </span>
          </div>
        </div>

        {/* Rating details */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 mt-2 mb-3 bg-white/5 rounded-xl px-3 py-1.5 border border-white/5">
          {business.google_rating !== undefined && (
            <div className="flex items-center gap-1.5">
              <span className="text-yellow-500">★</span>
              <span>G: <strong className="text-white">{business.google_rating}</strong> <span className="opacity-60">({business.review_count || 0})</span></span>
            </div>
          )}
          {business.jd_rating !== undefined && (
            <div className={`flex items-center gap-1.5 ${business.google_rating !== undefined ? 'border-l border-slate-700 pl-3' : ''}`}>
              <span className="text-orange-500">★</span>
              <span>JD: <strong className="text-white">{business.jd_rating}</strong> <span className="opacity-60">({business.jd_reviews_count || 0})</span></span>
              {business.jd_verified && <span className="text-[9px] text-green-400 bg-green-500/15 px-1 rounded font-bold uppercase">Ver</span>}
            </div>
          )}
        </div>

        <div className="space-y-3 mt-6">
          <div className="flex flex-wrap gap-2">
            {business.likely_service_match.map(service => (
              <span key={service} className="px-3 py-1 rounded-full bg-white/10 text-white text-xs font-medium uppercase tracking-wide border border-white/5">
                {service}
              </span>
            ))}
          </div>

          <div className="pt-4 border-t border-white/10">
            <p className="text-slate-400 text-sm line-clamp-2">
              <strong className="text-slate-300">Top Pain Point:</strong> {business.detected_pain_points?.[0] || "None detected"}
            </p>
          </div>


        </div>
      </div>
    </Link>
  );
}
