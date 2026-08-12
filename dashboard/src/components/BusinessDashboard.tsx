"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import BusinessCard from "./BusinessCard";
import { ScoringResult } from "@/types";
import { MOCK_BUSINESSES } from "@/lib/mockData";

// Load categories & locations JSON using require to avoid type issues
const categories = require("../data/categories.json") as Record<string, string[]>;
const locations = require("../data/locations.json") as Record<string, string[]>;

const allCategoryValues = Object.values(categories).flat();
const allStateNames = Object.keys(locations);

interface SelectedCell {
  cellId: string;
  rowIdx: number;
  colKey: string;
  label: string;
  value: string;
}

interface InlineEditState {
  rowId: string;
  field: string;
  value: string;
}

export default function BusinessDashboard({ initialBusinesses }: { initialBusinesses: ScoringResult[] }) {
  // Use mock data fallback if initialBusinesses is empty on load
  const initialList = initialBusinesses && initialBusinesses.length > 0 ? initialBusinesses : MOCK_BUSINESSES;

  // Navigation & View Mode state
  const [activeTab, setActiveTab] = useState<"overview" | "excel" | "growth" | "customers" | "reports">("overview");
  const [activeSheet, setActiveSheet] = useState<"all" | "high_opp" | "contacted" | "logs">("all");

  const [displayLimit, setDisplayLimit] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [businesses, setBusinesses] = useState<ScoringResult[]>(initialList);

  // Row Selection & Batch Action State
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());

  // Inline Cell Editing State
  const [editingCell, setEditingCell] = useState<InlineEditState | null>(null);

  // Real-time Scraping & Live Highlighting State
  const [isScraping, setIsScraping] = useState(false);
  const [recentlyScrapedIds, setRecentlyScrapedIds] = useState<Set<string>>(new Set());
  const prevBusinessIdsRef = useRef<Set<string>>(new Set(initialList.map(b => b.id)));

  // Excel Formula Bar & Selected Cell State
  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>({
    cellId: "A1",
    rowIdx: 0,
    colKey: "business_name",
    label: "Business Name",
    value: initialList[0]?.business_name || "No data selected"
  });

  // Real-time Console Log State
  const [showLogs, setShowLogs] = useState(false);
  const [logLines, setLogLines] = useState<string[]>([]);
  const consoleEndRef = useRef<HTMLDivElement>(null);

  // Scraper Form Drawer State
  const [showScraperModal, setShowScraperModal] = useState(false);
  const [formData, setFormData] = useState({
    category: "",
    city: "",
    state: "",
    country: "India",
    limit: 0,
    source: "gmaps"
  });

  // Category & Location Helper Presets
  const isPresetCategory = formData.category === "" || formData.category === "ALL" || allCategoryValues.includes(formData.category);
  const isPresetState = formData.state === "" || allStateNames.includes(formData.state);
  const citiesForState = isPresetState && formData.state ? (locations[formData.state] || []) : [];
  const isPresetCity = formData.city === "" || (isPresetState && citiesForState.includes(formData.city));

  // Stable helper: Fetch latest businesses from database
  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch("/api/businesses");
      if (!res.ok) return;
      const data = await res.json();
      if (data.success && Array.isArray(data.businesses)) {
        const realBizList: ScoringResult[] = data.businesses;
        
        if (realBizList.length > 0) {
          setBusinesses([...realBizList]);

          // Detect new incoming business IDs for live glow effect
          const currentIds = new Set(realBizList.map(b => b.id));
          const freshIds = new Set<string>();
          currentIds.forEach(id => {
            if (!prevBusinessIdsRef.current.has(id)) {
              freshIds.add(id);
            }
          });

          if (freshIds.size > 0) {
            setRecentlyScrapedIds(prev => new Set([...Array.from(prev), ...Array.from(freshIds)]));
            setTimeout(() => {
              setRecentlyScrapedIds(prev => {
                const updated = new Set(prev);
                freshIds.forEach(id => updated.delete(id));
                return updated;
              });
            }, 10000);
          }

          prevBusinessIdsRef.current = currentIds;
        }
      }
    } catch (err) {}
  }, []);

  // Initial mount fetch to populate live DB data immediately
  useEffect(() => {
    fetchLatest();
  }, [fetchLatest]);

  // 1. Poll /api/status to sync UI with backend scraper process
  useEffect(() => {
    let active = true;
    const checkStatus = async () => {
      try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const data = await res.json();
        if (active && typeof data.is_running === "boolean") {
          setIsScraping(data.is_running);
        }
      } catch (err) {}
    };

    checkStatus();
    const interval = setInterval(checkStatus, 2000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // 2. Continuous Real-time Live Fetching (every 1000ms during scrape, 2000ms normally)
  useEffect(() => {
    fetchLatest();
    const intervalTime = isScraping ? 1000 : 2000;
    const interval = setInterval(fetchLatest, intervalTime);
    return () => {
      clearInterval(interval);
    };
  }, [isScraping, fetchLatest]);


  // 3. Log SSE Stream with INSTANT Real-Time Data Refresh Trigger
  useEffect(() => {
    if (!isScraping && !showLogs && activeSheet !== "logs") return;

    const eventSource = new EventSource("/api/logs");
    eventSource.onmessage = (event) => {
      const line = event.data;
      if (line) {
        setLogLines((prev) => {
          const next = [...prev, line];
          if (next.length > 500) next.shift();
          return next;
        });

        // Refetch latest rows immediately as log events arrive
        fetchLatest();
      }
    };

    eventSource.onerror = (err) => console.warn("Logs SSE error:", err);
    return () => {
      eventSource.close();
    };
  }, [isScraping, showLogs, activeSheet, fetchLatest]);

  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollTop = consoleEndRef.current.scrollHeight;
    }
  }, [logLines, showLogs, activeSheet]);

  const triggerScrape = async () => {
    setIsScraping(true);
    setShowLogs(true);
    setLogLines([]);
    // Clear search and filters so newly scraped rows are immediately visible
    setSearchQuery("");
    setStatusFilter("all");
    setSourceFilter("all");

    try {
      const res = await fetch("/api/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: formData.category,
          city: formData.city,
          state: formData.state,
          country: formData.country,
          limit: formData.limit,
          source: formData.source
        })
      });
      const data = await res.json();
      if (data.success) {
        setShowScraperModal(false);
      } else {
        alert(data.message || "Failed to start scraper.");
        setIsScraping(false);
      }
    } catch (err) {
      alert("Network error starting scraper.");
      setIsScraping(false);
    }
  };

  const stopScrape = async () => {
    try {
      const res = await fetch("/api/stop", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setIsScraping(false);
        alert("🛑 Scraper sequence terminated!");
      } else {
        alert(data.message || "Failed to stop scraper process.");
      }
    } catch (err) {
      alert("Network error stopping scraper.");
    }
  };

  const clearDBAndRescrape = async () => {
    if (!confirm("Are you sure you want to DELETE ALL database records and re-trigger scraping?")) return;

    try {
      const delRes = await fetch("/api/businesses", { method: "DELETE" });
      const delData = await delRes.json();
      if (!delData.success) {
        alert("Error clearing database: " + delData.error);
        return;
      }
      setBusinesses(MOCK_BUSINESSES);
      setSelectedRowIds(new Set());
      setLogLines([]);
      prevBusinessIdsRef.current.clear();
      setRecentlyScrapedIds(new Set());
      alert("Database cleared! Triggering fresh scrape sequence...");
      await triggerScrape();
    } catch (err) {
      alert("Network error resetting database.");
    }
  };

  // Row Multi-Select Handlers
  const toggleSelectRow = (id: string) => {
    setSelectedRowIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedRowIds.size === displayedBusinesses.length) {
      setSelectedRowIds(new Set());
    } else {
      setSelectedRowIds(new Set(displayedBusinesses.map(b => b.id)));
    }
  };

  // Single Row Delete Handler
  const deleteSingleRow = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to DELETE "${name}"?`)) return;

    // Optimistically update UI state immediately
    setBusinesses(prev => prev.filter(b => b.id !== id));
    setSelectedRowIds(prev => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });

    try {
      await fetch(`/api/businesses/${id}`, { method: "DELETE" });
    } catch (err) {}
  };

  // Batch Delete Handler
  const deleteSelectedRows = async () => {
    const ids = Array.from(selectedRowIds);
    if (ids.length === 0) return;

    if (!confirm(`Are you sure you want to DELETE ${ids.length} selected lead(s)?`)) return;

    const idsToDeleteSet = new Set(ids);
    // Optimistically update UI state immediately
    setBusinesses(prev => prev.filter(b => !idsToDeleteSet.has(b.id)));
    setSelectedRowIds(new Set());

    try {
      await fetch("/api/businesses/batch-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids })
      });
    } catch (err) {}
  };


  // Inline Field Edit Save Handler
  const saveInlineEdit = async () => {
    if (!editingCell) return;
    const { rowId, field, value } = editingCell;

    try {
      const res = await fetch(`/api/businesses/${rowId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value })
      });
      const data = await res.json();
      if (data.success) {
        setBusinesses(prev => prev.map(b => b.id === rowId ? { ...b, [field]: value } : b));
        setEditingCell(null);
      }
    } catch (err) {
      setEditingCell(null);
    }
  };

  const updateOutreachStatus = async (businessId: string, newStatus: string) => {
    try {
      const res = await fetch(`/api/businesses/${businessId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outreach_status: newStatus })
      });
      const data = await res.json();
      if (data.success) {
        setBusinesses(prev => prev.map(b => b.id === businessId ? { ...b, outreach_status: newStatus } : b));
      }
    } catch (err) {}
  };

  const batchUpdateStatus = async (newStatus: string) => {
    const ids = Array.from(selectedRowIds);
    if (ids.length === 0) return;
    for (const id of ids) {
      await updateOutreachStatus(id, newStatus);
    }
  };

  const exportToCSV = (onlySelected = false) => {
    const sourceList = onlySelected ? displayedBusinesses.filter(b => selectedRowIds.has(b.id)) : displayedBusinesses;
    const headers = [
      "Business Name", "Category", "Phone", "Emails", "Website", "Address",
      "Rating", "Reviews", "Opp Score", "Urgency", "Status", "CMS", "Tech Stack"
    ];
    const rows = sourceList.map(b => [
      `"${(b.business_name || '').replace(/"/g, '""')}"`,
      `"${(b.category || '').replace(/"/g, '""')}"`,
      `"${(b.phone || 'N/A').replace(/"/g, '""')}"`,
      `"${(b.extracted_emails || []).join(" | ").replace(/"/g, '""')}"`,
      b.website_url || "N/A",
      `"${(b.address || 'N/A').replace(/"/g, '""')}"`,
      b.google_rating ?? "N/A",
      b.review_count ?? 0,
      b.opportunity_score ?? 0,
      b.outreach_urgency || "normal",
      b.outreach_status || "new",
      b.cms || "None",
      b.frontend_framework || "None"
    ]);

    const csvContent = [headers, ...rows].map(e => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `profitize_leads_${onlySelected ? 'selected' : 'export'}_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Metrics
  const totalLeads = businesses.length;
  const newLeads = businesses.filter(b => (b.outreach_status || 'new') === 'new').length;
  const contactedLeads = businesses.filter(b => b.outreach_status === 'contacted' || b.outreach_status === 'followed_up').length;
  const highOppLeads = businesses.filter(b => (b.opportunity_score || 0) >= 60).length;

  const filtered = useMemo(() => {
    return businesses.filter(b => {
      if (activeSheet === "high_opp" && (b.opportunity_score || 0) < 60) return false;
      if (activeSheet === "contacted" && b.outreach_status !== "contacted" && b.outreach_status !== "followed_up") return false;

      const matchesSearch = !searchQuery ||
        b.business_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (b.website_url || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        (b.category || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        (b.phone || "").includes(searchQuery);

      const matchesStatus = statusFilter === "all" || (b.outreach_status || "new") === statusFilter;
      const matchesSource = sourceFilter === "all" || (b.source_platforms && b.source_platforms.includes(sourceFilter));

      return matchesSearch && matchesStatus && matchesSource;
    });
  }, [businesses, activeSheet, searchQuery, statusFilter, sourceFilter]);

  const displayedBusinesses = displayLimit === null ? filtered : filtered.slice(0, displayLimit);
  const isAllSelected = displayedBusinesses.length > 0 && selectedRowIds.size === displayedBusinesses.length;

  // Excel columns definition
  const excelColumns = [
    { key: "business_name", colLetter: "A", name: "Business Name", width: "w-56" },
    { key: "category", colLetter: "B", name: "Category", width: "w-36" },
    { key: "phone", colLetter: "C", name: "Phone Number", width: "w-36" },
    { key: "extracted_emails", colLetter: "D", name: "Extracted Emails", width: "w-52" },
    { key: "website_url", colLetter: "E", name: "Website URL", width: "w-48" },
    { key: "address", colLetter: "F", name: "Address", width: "w-48" },
    { key: "ratings", colLetter: "G", name: "Rating & Reviews", width: "w-32" },
    { key: "opportunity_score", colLetter: "H", name: "Opp Score", width: "w-28" },
    { key: "intent_urgency", colLetter: "I", name: "Urgency / Intent", width: "w-32" },
    { key: "outreach_status", colLetter: "J", name: "Status", width: "w-36" },
    { key: "tech_stack", colLetter: "K", name: "Tech Stack", width: "w-44" },
    { key: "actions", colLetter: "L", name: "Action", width: "w-28" },
  ];

  const handleCellClick = (rowIdx: number, colLetter: string, colKey: string, label: string, valStr: string) => {
    const cellId = `${colLetter}${rowIdx + 1}`;
    setSelectedCell({ cellId, rowIdx, colKey, label, value: valStr });
  };

  // Monthly bar chart data
  const chartMonths = [
    { name: "Jan", val1: 40, val2: 47 },
    { name: "Feb", val1: 46, val2: 61 },
    { name: "Mar", val1: 37, val2: 41 },
    { name: "Apr", val1: 35, val2: 43 },
    { name: "May", val1: 28, val2: 45, highlighted: true },
    { name: "Jun", val1: 36, val2: 43 },
    { name: "Jul", val1: 48, val2: 53 },
    { name: "Aug", val1: 35, val2: 48 },
  ];

  return (
    <div className="flex min-h-screen bg-[#f4f5f9] text-slate-800 font-sans antialiased">
      
      {/* ============================================================= */}
      {/* LEFT SIDEBAR (Dark Charcoal / Navy #13141f)                  */}
      {/* ============================================================= */}
      <aside className="w-60 bg-[#13141f] text-slate-300 flex flex-col justify-between p-6 shrink-0 min-h-screen select-none">
        <div>
          {/* Brand Logo Header */}
          <div className="flex items-center gap-3 mb-10 pl-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="6" cy="6" r="3" />
                <circle cx="18" cy="6" r="3" />
                <circle cx="12" cy="18" r="3" />
                <path d="M6 6L18 6L12 18Z" fill="none" stroke="currentColor" strokeWidth="2" />
              </svg>
            </div>
            <span className="text-xl font-bold tracking-tight text-white font-sans">profitize</span>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-2">
            <button
              onClick={() => setActiveTab("overview")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm transition-all ${
                activeTab === "overview" ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              Overview
            </button>

            <button
              onClick={() => setActiveTab("excel")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm transition-all ${
                activeTab === "excel" ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Excel Grid View
            </button>

            <button
              onClick={() => setActiveTab("growth")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm transition-all ${
                activeTab === "growth" ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
              Growth
            </button>

            <button
              onClick={() => setActiveTab("customers")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm transition-all ${
                activeTab === "customers" ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              Customers
            </button>

            <button
              onClick={() => setActiveTab("reports")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm transition-all ${
                activeTab === "reports" ? "bg-white/10 text-white shadow-sm" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Reports
            </button>

            <div className="pt-6 space-y-2 border-t border-slate-800/80">
              <button
                onClick={() => setShowLogs(!showLogs)}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm text-slate-400 hover:text-white hover:bg-white/5 transition-all"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                Support & Console
              </button>

              <button
                onClick={() => setShowScraperModal(true)}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm text-slate-400 hover:text-white hover:bg-white/5 transition-all"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                </svg>
                Settings & Scraper
              </button>
            </div>
          </nav>
        </div>

        {/* Sidebar Footer Log out */}
        <div className="pt-6 border-t border-slate-800/80">
          <button
            onClick={clearDBAndRescrape}
            className="flex items-center gap-3 px-4 py-2 text-slate-400 hover:text-white font-medium text-sm transition-all"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Reset Pipeline
          </button>
        </div>
      </aside>

      {/* ============================================================= */}
      {/* MAIN DASHBOARD CONTENT AREA                                   */}
      {/* ============================================================= */}
      <main className="flex-1 p-8 overflow-y-auto max-w-[1600px] mx-auto">

        {/* FLOATING MULTI-ROW SELECTION TOOLBAR */}
        {selectedRowIds.size > 0 && (
          <div className="mb-6 bg-slate-900 text-white rounded-2xl p-4 shadow-xl border border-slate-800 flex items-center justify-between gap-4 animate-in fade-in slide-in-from-top-4">
            <div className="flex items-center gap-3">
              <span className="bg-indigo-600 text-white font-black text-xs px-3 py-1 rounded-lg">
                {selectedRowIds.size} {selectedRowIds.size === 1 ? "Lead" : "Leads"} Selected
              </span>
              <span className="text-xs text-slate-400 font-medium">Select actions to apply to all highlighted rows</span>
            </div>

            <div className="flex items-center gap-3 text-xs font-bold">
              {/* Batch Status Change */}
              <select
                onChange={(e) => {
                  if (e.target.value) batchUpdateStatus(e.target.value);
                }}
                className="bg-slate-800 text-white border border-slate-700 rounded-xl px-3 py-1.5 focus:outline-none"
              >
                <option value="">Change Status...</option>
                <option value="new">Mark NEW</option>
                <option value="contacted">Mark CONTACTED</option>
                <option value="followed_up">Mark FOLLOWED UP</option>
                <option value="closed">Mark CLOSED</option>
              </select>

              {/* Batch Export */}
              <button
                onClick={() => exportToCSV(true)}
                className="bg-emerald-700 hover:bg-emerald-600 text-white px-3 py-1.5 rounded-xl transition-all"
              >
                Export Selected ({selectedRowIds.size})
              </button>

              {/* Batch Delete */}
              <button
                onClick={deleteSelectedRows}
                className="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-xl transition-all flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete Selected ({selectedRowIds.size})
              </button>

              {/* Deselect All */}
              <button
                onClick={() => setSelectedRowIds(new Set())}
                className="text-slate-400 hover:text-white px-2 py-1"
              >
                Deselect All
              </button>
            </div>
          </div>
        )}
        
        {/* VIEW 1: OVERVIEW DASHBOARD */}
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            
            {/* LEFT COLUMN: Overview, KPIs Card, Analytics Donut Card */}
            <div className="lg:col-span-4 space-y-8">
              
              <div>
                <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Overview</h1>
              </div>

              {/* KPIs Card */}
              <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100/80 space-y-6">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-extrabold text-slate-900">KPIs</h3>
                  <button className="text-slate-400 hover:text-slate-600 font-bold">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z" />
                    </svg>
                  </button>
                </div>

                <div className="space-y-5 pt-2">
                  <div className="flex justify-between items-center border-b border-slate-100 pb-4">
                    <div>
                      <p className="text-xs font-semibold text-slate-400 mb-1">Current MRR</p>
                      <p className="text-2xl font-black text-slate-900">${(totalLeads * 7.1).toFixed(1)}k</p>
                    </div>
                    <span className="bg-[#dcfce7] text-[#166534] text-xs font-bold px-2.5 py-1 rounded-md flex items-center gap-1">
                      ↗ 16%
                    </span>
                  </div>

                  <div className="flex justify-between items-center border-b border-slate-100 pb-4">
                    <div>
                      <p className="text-xs font-semibold text-slate-400 mb-1">Current Customers</p>
                      <p className="text-2xl font-black text-slate-900">{totalLeads > 0 ? totalLeads.toLocaleString() : "0"}</p>
                    </div>
                    <span className="bg-[#dcfce7] text-[#166534] text-xs font-bold px-2.5 py-1 rounded-md flex items-center gap-1">
                      ↗ 17%
                    </span>
                  </div>

                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-xs font-semibold text-slate-400 mb-1">Active Customers</p>
                      <p className="text-2xl font-black text-slate-900">73.57%</p>
                    </div>
                    <span className="bg-[#fef9c3] text-[#854d0e] text-xs font-bold px-2.5 py-1 rounded-md flex items-center gap-1">
                      ↗ 21%
                    </span>
                  </div>
                </div>
              </div>

              {/* Analytics Donut Card */}
              <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100/80 space-y-6">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-extrabold text-slate-900">Analytics</h3>
                  <button className="text-slate-400 hover:text-slate-600 font-bold">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z" />
                    </svg>
                  </button>
                </div>

                <div className="flex justify-center items-center py-4 relative">
                  <svg className="w-48 h-48 transform -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="34" fill="transparent" stroke="#c3dafe" strokeWidth="16" strokeDasharray="118 97" strokeDashoffset="0" />
                    <circle cx="50" cy="50" r="34" fill="transparent" stroke="#b2f5ea" strokeWidth="16" strokeDasharray="71 144" strokeDashoffset="-118" />
                    <circle cx="50" cy="50" r="34" fill="transparent" stroke="#1e293b" strokeWidth="16" strokeDasharray="24 191" strokeDashoffset="-189" />
                  </svg>
                </div>

                <div className="flex items-center justify-around text-xs font-bold text-slate-700 pt-2">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-[#c3dafe]" />
                    <span>Sales</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-[#b2f5ea]" />
                    <span>Distribute</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-[#1e293b]" />
                    <span>Returns</span>
                  </div>
                </div>
              </div>

            </div>

            {/* RIGHT COLUMN: Growth Chart & REAL-TIME RECENT ACTIVITY TABLE */}
            <div className="lg:col-span-8 space-y-8">
              
              {/* Header Controls */}
              <div className="flex items-center justify-between gap-4">
                <div className="relative flex-1 max-w-md">
                  <input
                    type="text"
                    placeholder="Search scraped leads..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-white border-0 shadow-sm rounded-2xl pl-4 pr-10 py-3 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300"
                  />
                  <svg className="w-5 h-5 text-slate-400 absolute right-3.5 top-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>

                <div className="flex items-center gap-4">
                  {isScraping ? (
                    <button
                      onClick={stopScrape}
                      className="bg-rose-600 hover:bg-rose-700 text-white font-bold px-4 py-2.5 rounded-2xl text-xs flex items-center gap-2 shadow-sm transition-all animate-pulse"
                    >
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12" rx="2" />
                      </svg>
                      Stop Scrape
                    </button>
                  ) : (
                    <button
                      onClick={() => setShowScraperModal(true)}
                      className="bg-[#13141f] text-white hover:bg-slate-800 font-bold px-4 py-2.5 rounded-2xl text-xs flex items-center gap-2 shadow-sm transition-all"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                      </svg>
                      New Scrape
                    </button>
                  )}

                  <button className="relative bg-white p-2.5 rounded-2xl shadow-sm border border-slate-100 text-slate-600 hover:text-slate-900">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                    </svg>
                    <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-rose-500" />
                  </button>

                  <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-2xl shadow-sm border border-slate-100 cursor-pointer">
                    <div className="w-8 h-8 rounded-full bg-indigo-200 overflow-hidden flex items-center justify-center font-bold text-indigo-700 text-xs">
                      EM
                    </div>
                    <span className="text-xs font-bold text-slate-800">Eva Murphy</span>
                    <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>
              </div>

              {/* Card 1: Growth Chart */}
              <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100/80 space-y-6">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-extrabold text-slate-900">This Year Growth</h3>
                  
                  <div className="flex items-center gap-2 bg-slate-100/80 px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 cursor-pointer">
                    <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <span>Jan 08 - Aug 08</span>
                    <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </div>

                <div className="relative pt-6 pb-2">
                  <div className="absolute inset-0 flex flex-col justify-between pointer-events-none text-[10px] font-semibold text-slate-300">
                    <div className="border-b border-dashed border-slate-100 pb-1">$70k</div>
                    <div className="border-b border-dashed border-slate-100 pb-1">$60k</div>
                    <div className="border-b border-dashed border-slate-100 pb-1">$50k</div>
                    <div className="border-b border-dashed border-slate-100 pb-1">$40k</div>
                    <div className="border-b border-dashed border-slate-100 pb-1">$30k</div>
                    <div className="border-b border-slate-200 pb-1">0</div>
                  </div>

                  <div className="relative z-10 flex justify-between items-end h-56 pt-6 px-4">
                    {chartMonths.map((m, idx) => (
                      <div key={idx} className="flex flex-col items-center gap-2 group relative">
                        {m.highlighted && (
                          <div className="absolute -top-16 left-1/2 -translate-x-1/2 bg-white shadow-xl rounded-xl p-3 border border-slate-100 z-20 text-[11px] min-w-[130px] font-sans">
                            <div className="font-bold text-slate-800 mb-1">May</div>
                            <div className="flex justify-between items-center gap-2">
                              <span className="flex items-center gap-1.5 text-slate-500 font-semibold">
                                <span className="w-2 h-2 bg-slate-900 rounded-sm" /> 2021
                              </span>
                              <span className="font-bold text-slate-900">$25,581.00</span>
                            </div>
                            <div className="flex justify-between items-center gap-2 mt-0.5">
                              <span className="flex items-center gap-1.5 text-slate-500 font-semibold">
                                <span className="w-2 h-2 bg-indigo-400 rounded-sm" /> 2022
                              </span>
                              <span className="font-bold text-slate-900">$47,921.00</span>
                            </div>
                          </div>
                        )}

                        <div className="flex items-end gap-1.5">
                          <div style={{ height: `${m.val1 * 2.6}px` }} className="w-4 bg-slate-900 rounded-t-sm transition-all group-hover:bg-slate-800" />
                          <div style={{ height: `${m.val2 * 2.6}px` }} className="w-4 rounded-t-sm border border-indigo-300 pattern-striped-purple transition-all" />
                        </div>

                        <span className="text-xs font-semibold text-slate-400 mt-2">{m.name}</span>
                      </div>
                    ))}
                  </div>

                </div>
              </div>

              {/* Card 2: REAL-TIME RECENT SCRAPED ACTIVITY TABLE */}
              <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100/80 space-y-6">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-3">
                    <h3 className="text-lg font-extrabold text-slate-900">Recent Scraped Activity</h3>
                    {isScraping && (
                      <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-2.5 py-0.5 rounded-full flex items-center gap-1 animate-pulse border border-emerald-300">
                        <span className="w-2 h-2 rounded-full bg-emerald-600 animate-ping" />
                        LIVE SCRAPING ACTIVE ({displayedBusinesses.length} LEADS)
                      </span>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-3 text-xs font-bold text-slate-500">
                    <span>{displayedBusinesses.length} Records</span>
                    <button
                      onClick={() => exportToCSV(false)}
                      className="text-emerald-700 hover:text-emerald-800 font-bold bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200"
                    >
                      Export CSV
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="text-slate-400 font-semibold border-b border-slate-100 pb-3">
                        <th className="pb-3 w-8">
                          <input
                            type="checkbox"
                            checked={isAllSelected}
                            onChange={toggleSelectAll}
                            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                          />
                        </th>
                        <th className="pb-3 font-semibold">Business Lead</th>
                        <th className="pb-3 font-semibold">Contact Info</th>
                        <th className="pb-3 font-semibold">Rating & Quality</th>
                        <th className="pb-3 font-semibold">Status</th>
                        <th className="pb-3 font-semibold text-right">Opp Score</th>
                        <th className="pb-3 font-semibold text-center w-16">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-800">
                      {displayedBusinesses.map((b, idx) => {
                        const avatarLetters = b.business_name.substring(0, 2).toUpperCase();
                        const isRecentlyAdded = recentlyScrapedIds.has(b.id);
                        const isSelected = selectedRowIds.has(b.id);
                        const rawFirstEmail = ((b.extracted_emails as any[]) || [])[0];
                        const firstEmail = typeof rawFirstEmail === 'string'
                          ? rawFirstEmail
                          : (rawFirstEmail && typeof rawFirstEmail === 'object' ? (rawFirstEmail.email || rawFirstEmail.address || null) : null);




                        return (
                          <tr
                            key={b.id || idx}
                            className={`transition-all ${
                              isSelected
                                ? 'bg-indigo-50/80 text-indigo-950 font-medium border-l-4 border-indigo-600'
                                : isRecentlyAdded
                                ? 'bg-emerald-50/90 text-emerald-950 font-bold shadow-sm border-l-4 border-emerald-500 animate-pulse'
                                : 'hover:bg-slate-50/80'
                            }`}
                          >
                            {/* Select Checkbox */}
                            <td className="py-3.5 pl-1">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleSelectRow(b.id)}
                                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                              />
                            </td>

                            {/* Business Lead Name & Source */}
                            <td className="py-3.5 font-bold">
                              <div className="flex items-center gap-3">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs shadow-inner font-extrabold ${
                                  isRecentlyAdded ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700'
                                }`}>
                                  {avatarLetters}
                                </div>
                                <div>
                                  <div className="flex items-center gap-2">
                                    <span className="font-bold text-slate-900 block">{b.business_name}</span>
                                    {isRecentlyAdded && (
                                      <span className="bg-emerald-500 text-white text-[9px] font-black px-1.5 py-0.2 rounded uppercase">
                                        ⚡ LIVE
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-2 mt-0.5">
                                    <span className="text-[10px] text-slate-400 font-normal">{b.category || "General"}</span>
                                    <span className="bg-slate-100 text-slate-500 text-[9px] px-1.5 py-0.2 rounded font-mono uppercase">
                                      {(b.source_platforms || ['gmaps'])[0]}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </td>

                            {/* Contact Info */}
                            <td className="py-3.5">
                              <div className="space-y-0.5">
                                {firstEmail ? (
                                  <div className="font-mono text-emerald-700 font-semibold">{firstEmail}</div>
                                ) : (
                                  <div className="text-slate-400 italic">No email</div>
                                )}
                                <div className="text-[11px] text-slate-500 font-mono">{b.phone || b.website_url || "No contact info"}</div>
                              </div>
                            </td>

                            {/* Rating & Reviews */}
                            <td className="py-3.5 font-mono">
                              {b.google_rating ? (
                                <span className="text-amber-600 font-bold">
                                  ⭐ {b.google_rating} <span className="text-slate-400 text-[10px]">({b.review_count ?? 0})</span>
                                </span>
                              ) : (
                                <span className="text-slate-400">—</span>
                              )}
                            </td>

                            {/* Status */}
                            <td className="py-3.5">
                              <span className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-700">
                                <span className={`w-2 h-2 rounded-sm ${
                                  (b.outreach_status || 'new') === 'new' ? 'bg-indigo-500' :
                                  b.outreach_status === 'contacted' ? 'bg-emerald-500' : 'bg-amber-500'
                                }`} />
                                {(b.outreach_status || 'New Lead').replace('_', ' ')}
                              </span>
                            </td>

                            {/* Opportunity Score */}
                            <td className="py-3.5 text-right font-black">
                              <span className={`inline-block px-3 py-1 rounded-lg text-xs font-extrabold shadow-sm ${
                                (b.opportunity_score || 0) >= 70
                                  ? 'bg-rose-100 text-rose-800 border border-rose-200'
                                  : (b.opportunity_score || 0) >= 40
                                  ? 'bg-amber-100 text-amber-800 border border-amber-200'
                                  : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                              }`}>
                                {b.opportunity_score ?? 'N/A'} / 100
                              </span>
                            </td>

                            {/* Single Row Actions */}
                            <td className="py-3.5 text-center">
                              <button
                                onClick={() => deleteSingleRow(b.id, b.business_name)}
                                title="Delete row"
                                className="text-slate-400 hover:text-rose-600 p-1 rounded hover:bg-rose-50 transition-all"
                              >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

              </div>

            </div>

          </div>
        )}

        {/* VIEW 2: EXCEL CELL GRID FORMAT VIEW */}
        {activeTab === "excel" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Excel Grid Spreadsheet</h2>
                <p className="text-xs text-slate-500">Interactive cell grid with inline editing, row selection & batch deletion</p>
              </div>
              <div className="flex items-center gap-2">
                {isScraping && (
                  <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-3 py-1 rounded-xl border border-emerald-300 flex items-center gap-1.5 animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-emerald-600 animate-ping" />
                    LIVE SCRAPING STREAM ({businesses.length} RECORDS)
                  </span>
                )}
                {isScraping ? (
                  <button
                    onClick={stopScrape}
                    className="bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs px-4 py-2 rounded-xl shadow transition-all flex items-center gap-1.5 animate-pulse"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                    Stop Scrape
                  </button>
                ) : (
                  <button
                    onClick={() => setShowScraperModal(true)}
                    className="bg-[#107c41] text-white font-bold text-xs px-4 py-2 rounded-xl shadow hover:bg-emerald-600 transition-all flex items-center gap-1.5"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    Trigger New Scrape
                  </button>
                )}
              </div>
            </div>

            {/* Excel Formula Bar */}
            <div className="bg-slate-900 text-white rounded-xl p-3 font-mono text-xs flex items-center gap-3">
              <div className="bg-emerald-600 px-3 py-1 rounded text-white font-bold">{selectedCell?.cellId || "A1"}</div>
              <div className="text-slate-400 font-bold">fx</div>
              <div className="flex-1 bg-slate-950 px-3 py-1 rounded text-slate-200 truncate">
                {selectedCell ? `${selectedCell.label}: ${selectedCell.value}` : "Select any cell..."}
              </div>
            </div>

            {/* Excel Cell Grid Table */}
            <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
              <div className="overflow-x-auto max-h-[600px]">
                <table className="w-full text-left border-collapse text-xs select-none">
                  <thead>
                    <tr className="bg-slate-100 border-b border-slate-300 font-mono text-slate-600 font-bold">
                      <th className="w-8 p-2 border-r border-slate-300 text-center">
                        <input
                          type="checkbox"
                          checked={isAllSelected}
                          onChange={toggleSelectAll}
                          className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                        />
                      </th>
                      <th className="w-10 p-2 border-r border-slate-300 text-center">#</th>
                      {excelColumns.map(c => (
                        <th key={c.colLetter} className="p-2 border-r border-slate-300 text-center text-emerald-700">
                          {c.colLetter}
                        </th>
                      ))}
                    </tr>
                    <tr className="bg-slate-50 border-b border-slate-300 text-slate-700 font-bold uppercase tracking-wider text-[10px]">
                      <th className="p-2 border-r border-slate-300 text-center">Select</th>
                      <th className="p-2 border-r border-slate-300 text-center">Row</th>
                      {excelColumns.map(c => (
                        <th key={c.key} className="p-2 border-r border-slate-300">{c.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {displayedBusinesses.map((b, rowIdx) => {
                      const isRecentlyAdded = recentlyScrapedIds.has(b.id);
                      const isSelected = selectedRowIds.has(b.id);

                      return (
                        <tr
                          key={b.id}
                          className={`transition-all ${
                            isSelected
                              ? 'bg-indigo-50/90 font-medium border-l-4 border-indigo-600'
                              : isRecentlyAdded
                              ? 'bg-emerald-100/80 animate-pulse border-l-4 border-emerald-600'
                              : 'hover:bg-emerald-50/30'
                          }`}
                        >
                          {/* Row Selection Checkbox */}
                          <td className="p-2 border-r border-slate-300 text-center bg-slate-50">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelectRow(b.id)}
                              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                            />
                          </td>

                          <td className="p-2 border-r border-slate-300 text-center font-mono text-slate-500 bg-slate-50">{rowIdx + 1}</td>
                          
                          {/* Col A: Business Name (Inline Edit) */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "A", "business_name", "Business Name", b.business_name)}
                            onDoubleClick={() => setEditingCell({ rowId: b.id, field: "business_name", value: b.business_name })}
                            className={`p-2 border-r border-slate-300 font-bold text-slate-900 cursor-pointer ${
                              selectedCell?.cellId === `A${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {editingCell?.rowId === b.id && editingCell?.field === "business_name" ? (
                              <div className="flex items-center gap-1">
                                <input
                                  type="text"
                                  value={editingCell.value}
                                  onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
                                  onKeyDown={(e) => e.key === "Enter" && saveInlineEdit()}
                                  className="w-full bg-white border border-slate-400 rounded px-1.5 py-0.5 text-xs font-bold focus:outline-none"
                                  autoFocus
                                />
                                <button onClick={saveInlineEdit} className="text-emerald-700 font-bold text-[10px]">Save</button>
                              </div>
                            ) : (
                              <div className="flex items-center justify-between group">
                                <div className="flex items-center gap-1.5">
                                  <span>{b.business_name}</span>
                                  {isRecentlyAdded && (
                                    <span className="bg-emerald-600 text-white text-[9px] font-black px-1 rounded uppercase">⚡ LIVE</span>
                                  )}
                                </div>
                                <button
                                  onClick={() => setEditingCell({ rowId: b.id, field: "business_name", value: b.business_name })}
                                  className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-700 text-[10px]"
                                >
                                  ✏️
                                </button>
                              </div>
                            )}
                          </td>

                          {/* Col B: Category (Inline Edit) */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "B", "category", "Category", b.category || "General")}
                            onDoubleClick={() => setEditingCell({ rowId: b.id, field: "category", value: b.category || "" })}
                            className={`p-2 border-r border-slate-300 text-slate-700 cursor-pointer ${
                              selectedCell?.cellId === `B${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {editingCell?.rowId === b.id && editingCell?.field === "category" ? (
                              <div className="flex items-center gap-1">
                                <input
                                  type="text"
                                  value={editingCell.value}
                                  onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
                                  onKeyDown={(e) => e.key === "Enter" && saveInlineEdit()}
                                  className="w-full bg-white border border-slate-400 rounded px-1.5 py-0.5 text-xs focus:outline-none"
                                  autoFocus
                                />
                                <button onClick={saveInlineEdit} className="text-emerald-700 font-bold text-[10px]">Save</button>
                              </div>
                            ) : (
                              b.category || "General"
                            )}
                          </td>

                          {/* Col C: Phone Number (Inline Edit) */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "C", "phone", "Phone Number", b.phone || "N/A")}
                            onDoubleClick={() => setEditingCell({ rowId: b.id, field: "phone", value: b.phone || "" })}
                            className={`p-2 border-r border-slate-300 font-mono text-slate-600 cursor-pointer ${
                              selectedCell?.cellId === `C${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {editingCell?.rowId === b.id && editingCell?.field === "phone" ? (
                              <div className="flex items-center gap-1">
                                <input
                                  type="text"
                                  value={editingCell.value}
                                  onChange={(e) => setEditingCell({ ...editingCell, value: e.target.value })}
                                  onKeyDown={(e) => e.key === "Enter" && saveInlineEdit()}
                                  className="w-full bg-white border border-slate-400 rounded px-1.5 py-0.5 text-xs font-mono focus:outline-none"
                                  autoFocus
                                />
                                <button onClick={saveInlineEdit} className="text-emerald-700 font-bold text-[10px]">Save</button>
                              </div>
                            ) : (
                              b.phone || "N/A"
                            )}
                          </td>

                          {/* Col D: Extracted Emails */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "D", "extracted_emails", "Extracted Emails", ((b.extracted_emails as any[]) || []).map((e: any) => typeof e === 'string' ? e : (e?.email || JSON.stringify(e))).join(", ") || "None")}
                            className={`p-2 border-r border-slate-300 font-mono text-emerald-600 cursor-pointer ${
                              selectedCell?.cellId === `D${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {(() => {
                              const item = ((b.extracted_emails as any[]) || [])[0];
                              if (!item) return <span className="text-slate-400 italic">No email</span>;
                              if (typeof item === 'string') return item;
                              if (typeof item === 'object' && item !== null) return ((item as any).email || (item as any).address || JSON.stringify(item));
                              return String(item);
                            })()}
                          </td>



                          {/* Col E: Website URL */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "E", "website_url", "Website URL", b.website_url || "None")}
                            className={`p-2 border-r border-slate-300 font-mono text-blue-600 cursor-pointer ${
                              selectedCell?.cellId === `E${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {b.website_url ? (
                              <a href={b.website_url.startsWith('http') ? b.website_url : `https://${b.website_url}`} target="_blank" rel="noreferrer" className="hover:underline truncate block">
                                {b.website_url.replace(/^https?:\/\//, '')}
                              </a>
                            ) : (
                              <span className="text-slate-400 italic">No website</span>
                            )}
                          </td>

                          {/* Col F: Address */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "F", "address", "Address", b.address || "N/A")}
                            className={`p-2 border-r border-slate-300 text-slate-500 cursor-pointer ${
                              selectedCell?.cellId === `F${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {b.address || "N/A"}
                          </td>

                          {/* Col G: Rating & Reviews */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "G", "ratings", "Rating & Reviews", `⭐ ${b.google_rating ?? 'N/A'} (${b.review_count ?? 0} reviews)`)}
                            className={`p-2 border-r border-slate-300 text-center font-bold text-amber-600 cursor-pointer ${
                              selectedCell?.cellId === `G${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            ⭐ {b.google_rating ?? 'N/A'} <span className="text-slate-400 text-[10px]">({b.review_count ?? 0})</span>
                          </td>

                          {/* Col H: Opp Score */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "H", "opportunity_score", "Opp Score", String(b.opportunity_score ?? 0))}
                            className={`p-2 border-r border-slate-300 text-center font-bold text-emerald-700 cursor-pointer ${
                              selectedCell?.cellId === `H${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {b.opportunity_score ?? 'N/A'}
                          </td>

                          {/* Col I: Urgency / Intent */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "I", "intent_urgency", "Urgency / Intent", b.outreach_urgency || "normal")}
                            className={`p-2 border-r border-slate-300 text-center uppercase font-bold text-[10px] text-slate-600 cursor-pointer ${
                              selectedCell?.cellId === `I${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {b.outreach_urgency || 'normal'}
                          </td>

                          {/* Col J: Status */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "J", "outreach_status", "Outreach Status", b.outreach_status || "new")}
                            className={`p-2 border-r border-slate-300 cursor-pointer ${
                              selectedCell?.cellId === `J${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            <select
                              value={b.outreach_status || "new"}
                              onChange={(e) => updateOutreachStatus(b.id, e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              className="bg-slate-100 border border-slate-300 text-slate-800 text-xs font-bold rounded px-1 py-0.5 cursor-pointer"
                            >
                              <option value="new">NEW</option>
                              <option value="contacted">CONTACTED</option>
                              <option value="followed_up">FOLLOWED UP</option>
                              <option value="closed">CLOSED</option>
                            </select>
                          </td>

                          {/* Col K: Tech Stack */}
                          <td
                            onClick={() => handleCellClick(rowIdx, "K", "tech_stack", "Tech Stack", `${b.cms || 'Custom'} (${b.frontend_framework || 'None'})`)}
                            className={`p-2 border-r border-slate-300 text-slate-600 cursor-pointer ${
                              selectedCell?.cellId === `K${rowIdx + 1}` ? 'ring-2 ring-emerald-600 bg-emerald-500/10 font-black' : ''
                            }`}
                          >
                            {b.cms || 'Custom'}
                          </td>

                          {/* Col L: Action & Delete */}
                          <td className="p-2 text-center">
                            <div className="flex items-center justify-center gap-1.5">
                              <a href={`/business/${b.id}`} className="bg-slate-900 text-white font-bold px-2 py-1 rounded text-[10px]">
                                View
                              </a>
                              <button
                                onClick={() => deleteSingleRow(b.id, b.business_name)}
                                title="Delete row"
                                className="text-slate-400 hover:text-rose-600 p-1 rounded hover:bg-rose-50 transition-all"
                              >
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}

                    {displayedBusinesses.length === 0 && (
                      <tr>
                        <td colSpan={14} className="p-8 text-center text-slate-400">
                          No scraped records match the current filters. Click <strong>"Trigger New Scrape"</strong> to gather fresh leads.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* SCRAPER CONFIGURATION MODAL WITH DEPENDENT STATE & CITY DROPDOWNS */}
      {showScraperModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-6">
            <div className="flex justify-between items-center border-b border-slate-100 pb-4">
              <h3 className="text-lg font-extrabold text-slate-900">Trigger Intelligence Scrape</h3>
              <button onClick={() => setShowScraperModal(false)} className="text-slate-400 hover:text-slate-700 font-bold">✕</button>
            </div>

            <div className="space-y-4 text-xs">
              {/* Category Dropdown */}
              <div>
                <label className="font-bold text-slate-700 block mb-1">Category</label>
                <select
                  value={isPresetCategory ? formData.category : "custom"}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value === "custom" ? "Custom Category" : e.target.value })}
                  className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none"
                >
                  <option value="">Select Category...</option>
                  <option value="ALL">All Categories</option>
                  {Object.entries(categories).map(([group, subcats]) => (
                    <optgroup key={group} label={group}>
                      {subcats.map((sub) => (
                        <option key={sub} value={sub}>{sub}</option>
                      ))}
                    </optgroup>
                  ))}
                  <option value="custom">Custom...</option>
                </select>

                {!isPresetCategory && formData.category !== "" && (
                  <input
                    placeholder="Enter custom category"
                    value={formData.category === "Custom Category" ? "" : formData.category}
                    onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value }))}
                    className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none mt-1"
                  />
                )}
              </div>

              {/* State & City Dependent Dropdowns */}
              <div className="grid grid-cols-2 gap-3">
                {/* State Dropdown */}
                <div>
                  <label className="font-bold text-slate-700 block mb-1">State</label>
                  <select
                    value={isPresetState ? formData.state : "custom"}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "custom") {
                        setFormData(prev => ({ ...prev, state: "Custom State", city: "" }));
                      } else {
                        const countryName = val.includes("(USA)") ? "United States" : "India";
                        setFormData(prev => ({ ...prev, state: val, city: "", country: countryName }));
                      }
                    }}
                    className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none font-medium"
                  >
                    <option value="">Select State...</option>
                    {allStateNames.map(st => (
                      <option key={st} value={st}>{st}</option>
                    ))}
                    <option value="custom">Custom State...</option>
                  </select>

                  {!isPresetState && formData.state !== "" && (
                    <input
                      placeholder="Enter state name"
                      value={formData.state === "Custom State" ? "" : formData.state}
                      onChange={(e) => setFormData(prev => ({ ...prev, state: e.target.value }))}
                      className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none mt-1"
                    />
                  )}
                </div>

                {/* City Dropdown (Populates after State is selected) */}
                <div>
                  <label className="font-bold text-slate-700 block mb-1">
                    City {formData.state ? `(${formData.state})` : ""}
                  </label>
                  <select
                    disabled={!formData.state}
                    value={isPresetCity ? formData.city : "custom"}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "custom") {
                        setFormData(prev => ({ ...prev, city: "Custom City" }));
                      } else {
                        setFormData(prev => ({ ...prev, city: val }));
                      }
                    }}
                    className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none disabled:opacity-50 font-medium"
                  >
                    {!formData.state ? (
                      <option value="">-- Select State First --</option>
                    ) : (
                      <>
                        <option value="">Select City...</option>
                        {citiesForState.map(ct => (
                          <option key={ct} value={ct}>{ct}</option>
                        ))}
                        <option value="custom">Custom City...</option>
                      </>
                    )}
                  </select>

                  {!isPresetCity && formData.city !== "" && (
                    <input
                      placeholder="Enter city name"
                      value={formData.city === "Custom City" ? "" : formData.city}
                      onChange={(e) => setFormData(prev => ({ ...prev, city: e.target.value }))}
                      className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none mt-1"
                    />
                  )}
                </div>
              </div>

              {/* Source & Max Results */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold text-slate-700 block mb-1">Source Platform</label>
                  <select
                    value={formData.source}
                    onChange={(e) => setFormData({ ...formData, source: e.target.value })}
                    className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none"
                  >
                    <option value="gmaps">Google Maps</option>
                    <option value="justdial">JustDial</option>
                    <option value="indiamart">IndiaMart</option>
                  </select>
                </div>
                <div>
                  <label className="font-bold text-slate-700 block mb-1">Max Results</label>
                  <select
                    value={formData.limit}
                    onChange={(e) => setFormData({ ...formData, limit: Number(e.target.value) })}
                    className="w-full bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none"
                  >
                    <option value={0}>All (Unlimited)</option>
                    <option value={5}>5 Results</option>
                    <option value={10}>10 Results</option>
                    <option value={25}>25 Results</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                onClick={() => setShowScraperModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-slate-500 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={triggerScrape}
                disabled={isScraping || !formData.state}
                className="bg-[#13141f] hover:bg-slate-800 disabled:opacity-50 text-white px-5 py-2 rounded-xl text-xs font-bold shadow transition-all"
              >
                {isScraping ? "Scraping..." : "Start Scrape"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REAL-TIME TERMINAL LOG MODAL */}
      {showLogs && (
        <div className="fixed bottom-4 right-4 w-96 bg-slate-950 border border-slate-800 text-white rounded-2xl shadow-2xl overflow-hidden z-40 font-mono text-xs">
          <div className="bg-slate-900 px-4 py-2 flex justify-between items-center border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span className="font-bold text-emerald-400">⚡ Live Scraper Output</span>
              {isScraping && (
                <button
                  onClick={stopScrape}
                  className="bg-rose-600 hover:bg-rose-700 text-white px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1"
                >
                  <span className="w-1.5 h-1.5 bg-white rounded-sm" /> Stop Process
                </button>
              )}
            </div>
            <button onClick={() => setShowLogs(false)} className="text-slate-500 hover:text-white font-bold">✕</button>
          </div>
          <div ref={consoleEndRef} className="p-3 h-48 overflow-y-auto space-y-1 text-slate-300">
            {logLines.map((l, i) => (
              <div key={i} className="text-[11px] leading-relaxed">{l}</div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
