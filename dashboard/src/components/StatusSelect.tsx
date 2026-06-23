"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function StatusSelect({ 
  businessId, 
  initialStatus 
}: { 
  businessId: string; 
  initialStatus: string; 
}) {
  const router = useRouter();
  const [status, setStatus] = useState(initialStatus);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const handleChange = async (newStatus: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch(`/api/businesses/${businessId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outreach_status: newStatus })
      });
      const data = await res.json();
      if (res.ok) {
        setStatus(newStatus);
        setMessage({ text: "Outreach status updated!", type: "success" });
        router.refresh(); // Refresh Server Component data to update total counts etc
      } else {
        setMessage({ text: data.error || "Failed to update status", type: "error" });
      }
    } catch (err) {
      setMessage({ text: "Network error updating status", type: "error" });
    } finally {
      setLoading(false);
      // Auto-clear message after 3 seconds
      setTimeout(() => setMessage(null), 3000);
    }
  };

  return (
    <div className="space-y-2">
      <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">
        Outreach Status
      </label>
      <div className="relative">
        <select
          value={status}
          disabled={loading}
          onChange={(e) => handleChange(e.target.value)}
          className={`w-full bg-slate-900 border border-slate-700 text-white rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all font-semibold cursor-pointer ${loading ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <option value="new">New</option>
          <option value="contacted">Contacted</option>
          <option value="followed_up">Followed Up</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      {message && (
        <p className={`text-xs font-medium ${message.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
          {message.text}
        </p>
      )}
    </div>
  );
}
