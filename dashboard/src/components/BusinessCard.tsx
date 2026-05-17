"use client";
import { ScoringResult } from "@/types";
import Link from "next/link";

function getScoreColor(score: number) {
  if (score >= 70) return "bg-red-500 text-white"; // High opportunity (bad website)
  if (score >= 40) return "bg-yellow-400 text-slate-900"; // Moderate
  return "bg-green-500 text-white"; // Low opportunity (good website)
}

export default function BusinessCard({ business }: { business: ScoringResult }) {
  return (
    <Link href={`/business/${business.id}`} className="block transition-transform hover:-translate-y-1">
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300 relative overflow-hidden group">

        {/* Decorative gradient blob */}
        <div className="absolute -right-10 -top-10 w-32 h-32 bg-blue-500/20 rounded-full blur-3xl group-hover:bg-blue-400/30 transition-all"></div>

        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-xl font-bold text-white mb-1">{business.business_name}</h3>
            {business.website_url ? (
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  window.open(business.website_url, "_blank");
                }}
                className="text-blue-400 text-sm hover:underline cursor-pointer"
              >
                {business.website_url.replace(/^https?:\/\//, '')}
              </div>
            ) : (
              <span className="text-red-400 text-sm font-medium">No Website Detected</span>
            )}
          </div>
          <div className={`flex flex-col items-center justify-center w-16 h-16 rounded-xl ${getScoreColor(business.opportunity_score)} shadow-lg`}>
            <span className="text-xs font-semibold opacity-80 uppercase tracking-wider">Opp</span>
            <span className="text-2xl font-black">{business.opportunity_score}</span>
          </div>
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
              <strong className="text-slate-300">Top Pain Point:</strong> {business.detected_pain_points[0] || "None detected"}
            </p>
          </div>
        </div>
      </div>
    </Link>
  );
}
