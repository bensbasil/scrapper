"use client";

import { useState } from "react";
import BusinessCard from "./BusinessCard";
import { ScoringResult } from "@/types";

export default function BusinessDashboard({ initialBusinesses }: { initialBusinesses: ScoringResult[] }) {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [limit, setLimit] = useState<number | "all">(10);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  
  // Scraper Form State
  const [isScraping, setIsScraping] = useState(false);
  const [formData, setFormData] = useState({
    category: "",
    city: "",
    state: "",
    country: "",
    limit: 5
  });

  const triggerScrape = async () => {
    setIsScraping(true);
    try {
      const res = await fetch("/api/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      const data = await res.json();
      if (data.success) {
        alert("Scraper started! The dashboard will update automatically as results come in.");
      } else {
        alert("Failed to start scraper: " + data.error);
      }
    } catch (err) {
      alert("Network error starting scraper.");
    } finally {
      setIsScraping(false);
    }
  };

  // Filter by search query, status, and source platform
  const filtered = initialBusinesses.filter(b => {
    const matchesSearch = b.business_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (b.website_url || "").toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || (b.outreach_status || "new") === statusFilter;
    
    const matchesSource = sourceFilter === "all" || 
      (b.source_platforms && b.source_platforms.includes(sourceFilter));
      
    return matchesSearch && matchesStatus && matchesSource;
  });

  const displayedBusinesses = limit === "all" ? filtered : filtered.slice(0, limit);

  const clearDatabase = async () => {
    if (!confirm("Are you sure you want to delete ALL scraped data? This cannot be undone.")) return;
    
    try {
      const res = await fetch("/api/businesses", { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        alert("Database cleared!");
        window.location.reload(); // Refresh to show empty state
      } else {
        alert("Error: " + data.error);
      }
    } catch (err) {
      alert("Network error clearing database.");
    }
  };

  const exportToCSV = () => {
    const headers = [
      "Business Name", 
      "Website", 
      "Opportunity Score", 
      "Outreach Status",
      "Extracted Emails", 
      "Tech Stack (CMS)", 
      "Tech Stack (Frontend)",
      "Tech Stack (Analytics)",
      "Decision Makers",
      "Pain Points"
    ];
    const rows = displayedBusinesses.map(b => [
      `"${b.business_name.replace(/"/g, '""')}"`,
      b.website_url || "N/A",
      b.opportunity_score,
      b.outreach_status || "new",
      `"${(b.extracted_emails || []).join(" | ").replace(/"/g, '""')}"`,
      b.cms || "None",
      b.frontend_framework || "None",
      `"${(b.analytics_tools || []).join(" | ").replace(/"/g, '""')}"`,
      `"${(b.decision_makers || []).map(dm => `${dm.name} (${dm.role})`).join(" | ").replace(/"/g, '""')}"`,
      `"${(b.detected_pain_points || []).join(" | ").replace(/"/g, '""')}"`
    ]);
    
    const csvContent = [headers, ...rows].map(e => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `prospects_export_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      
      {/* Scraper Control Panel */}
      <div className="bg-gradient-to-r from-blue-600/10 to-indigo-600/10 border border-blue-500/20 rounded-2xl p-6 backdrop-blur-xl shadow-2xl">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-blue-500 p-2 rounded-lg shadow-lg shadow-blue-500/20">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Trigger New Intelligence Scrape</h3>
            <p className="text-xs text-slate-400">Specify your niche and location to start gathering leads.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
          <div className="space-y-1">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 ml-1">Category (Optional)</label>
            <input 
              placeholder="e.g. Gyms" 
              value={formData.category}
              onChange={(e) => setFormData({...formData, category: e.target.value})}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 ml-1">City</label>
            <input 
              placeholder="e.g. Trivandrum" 
              value={formData.city}
              onChange={(e) => setFormData({...formData, city: e.target.value})}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 ml-1">State</label>
            <input 
              placeholder="e.g. Kerala" 
              value={formData.state}
              onChange={(e) => setFormData({...formData, state: e.target.value})}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 ml-1">Country</label>
            <input 
              placeholder="e.g. India" 
              value={formData.country}
              onChange={(e) => setFormData({...formData, country: e.target.value})}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 ml-1">Max Results</label>
            <div className="flex gap-2">
              <select
                value={[0, 1, 3, 5, 10].includes(formData.limit) ? formData.limit : "custom"}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "custom") {
                    setFormData({...formData, limit: 15}); // Default custom scraping limit
                  } else {
                    setFormData({...formData, limit: Number(val)});
                  }
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
              >
                <option value={1}>1 Result</option>
                <option value={3}>3 Results</option>
                <option value={5}>5 Results</option>
                <option value={10}>10 Results</option>
                <option value={0}>All Results</option>
                <option value="custom">Custom...</option>
              </select>
              
              {![0, 1, 3, 5, 10].includes(formData.limit) && (
                <input 
                  type="number"
                  min={1}
                  placeholder="Num"
                  value={formData.limit}
                  onChange={(e) => setFormData({...formData, limit: Math.max(1, parseInt(e.target.value) || 1)})}
                  className="w-20 bg-slate-950 border border-slate-800 rounded-xl px-2 py-2 text-sm text-white focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
                />
              )}
            </div>
          </div>
          <div className="flex items-end">
            <button 
              onClick={triggerScrape}
              disabled={isScraping || (!formData.category && !formData.city && !formData.state && !formData.country)}
              className={`w-full h-[42px] rounded-xl font-bold text-sm transition-all shadow-lg ${isScraping ? 'bg-slate-700 text-slate-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-500/20 active:scale-95'}`}
            >
              {isScraping ? "Scraping..." : "Start Scrape"}
            </button>
          </div>
        </div>
      </div>
      {/* Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white/5 p-4 rounded-2xl border border-white/10 backdrop-blur-md">
        <div className="flex flex-wrap items-center gap-4 flex-1">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[250px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input 
              type="text" 
              placeholder="Search by name or website..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-slate-500"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">Status:</span>
            <select 
              value={statusFilter} 
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-white text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              <option value="all">All Statuses</option>
              <option value="new">New</option>
              <option value="contacted">Contacted</option>
              <option value="followed_up">Followed Up</option>
              <option value="closed">Closed</option>
            </select>
          </div>

          {/* Source Filter */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">Source:</span>
            <select 
              value={sourceFilter} 
              onChange={(e) => setSourceFilter(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-white text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              <option value="all">All Sources</option>
              <option value="google_maps">Google Maps</option>
              <option value="justdial">JustDial</option>
              <option value="indiamart">IndiaMart</option>
            </select>
          </div>

          <div className="flex bg-slate-900 rounded-lg p-1 border border-slate-700">
            <button 
              onClick={() => setViewMode("grid")}
              className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${viewMode === "grid" ? "bg-blue-500 text-white shadow-lg" : "text-slate-400 hover:text-white"}`}
            >
              GRID
            </button>
            <button 
              onClick={() => setViewMode("list")}
              className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${viewMode === "list" ? "bg-blue-500 text-white shadow-lg" : "text-slate-400 hover:text-white"}`}
            >
              LIST
            </button>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">Show:</span>
            <select 
              value={["all", 3, 10, 25, 50, 100].includes(limit) ? limit : "custom"} 
              onChange={(e) => {
                const val = e.target.value;
                if (val === "custom") {
                  setLimit(5); // Default custom value
                } else {
                  setLimit(val === "all" ? "all" : Number(val));
                }
              }}
              className="bg-slate-900 border border-slate-700 text-white text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value={3}>3</option>
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value="all">All</option>
              <option value="custom">Custom...</option>
            </select>
            
            {!["all", 3, 10, 25, 50, 100].includes(limit) && (
              <input
                type="number"
                min={1}
                value={limit}
                onChange={(e) => setLimit(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-16 bg-slate-900 border border-slate-700 text-white text-xs rounded-lg px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Limit"
              />
            )}
          </div>
        </div>

        <div className="flex gap-2">
          <button 
            onClick={clearDatabase}
            className="bg-transparent hover:bg-red-500/10 text-red-400 border border-red-500/20 px-4 py-2 rounded-xl text-sm font-bold transition-all flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Clear All
          </button>
          
          <button 
            onClick={exportToCSV}
            className="bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded-xl text-sm font-bold transition-all flex items-center gap-2 shadow-lg shadow-green-900/20"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Export CSV
          </button>
        </div>
      </div>

      {/* Main View */}
      {viewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {displayedBusinesses.map((biz) => (
            <BusinessCard key={biz.id} business={biz} />
          ))}
        </div>
      ) : (
        <div className="bg-slate-900/50 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-sm">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-white/10 bg-white/5">
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Business Name</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Website</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest text-center">Score</th>
                <th className="p-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Top Pain Point</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {displayedBusinesses.map((biz) => (
                <tr key={biz.id} className="hover:bg-white/5 transition-colors cursor-pointer group">
                  <td className="p-4">
                    <div className="font-bold text-white group-hover:text-blue-400 transition-colors">{biz.business_name}</div>
                    {biz.source_platforms && biz.source_platforms.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {biz.source_platforms.map(source => {
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
                              className={`text-[8px] px-1.5 py-0.2 rounded border font-semibold uppercase tracking-wider ${colors[source] || "bg-slate-500/10 text-slate-400 border-slate-500/20"}`}
                            >
                              {label[source] || source}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </td>
                  <td className="p-4">
                    <span className="text-slate-400 text-sm">{biz.website_url || "None"}</span>
                  </td>
                  <td className="p-4 text-center">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-black ${biz.opportunity_score > 60 ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>
                      {biz.opportunity_score}
                    </span>
                  </td>
                  <td className="p-4">
                    <span className="text-slate-300 text-sm line-clamp-1">{biz.detected_pain_points[0] || "No issues"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {displayedBusinesses.length === 0 && (
        <div className="text-center py-20 bg-white/5 border border-dashed border-white/10 rounded-2xl">
          <p className="text-slate-400">No businesses found.</p>
        </div>
      )}
    </div>
  );
}
