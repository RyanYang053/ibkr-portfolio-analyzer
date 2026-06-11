"use client";

import { useState } from "react";
import { Sparkles, Sun, Sunset, Moon, RefreshCw, CheckCircle } from "lucide-react";
import { triggerScheduledAnalyze } from "@/lib/api";

interface AnalysisRun {
  timestamp: string;
  period: "morning" | "midday" | "night";
  net_liquidation: number;
  cash: number;
  analysis_text: string;
}

interface DailyActionsPanelProps {
  initialRuns: AnalysisRun[];
}

export function DailyActionsPanel({ initialRuns }: DailyActionsPanelProps) {
  const [runs, setRuns] = useState<AnalysisRun[]>(initialRuns);
  const [activeTab, setActiveTab] = useState<"morning" | "midday" | "night">("morning");
  const [isLoading, setIsLoading] = useState(false);

  // Get the latest run for the active period
  const activeRun = runs
    .filter((r) => r.period === activeTab)
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0];

  async function handleRefresh() {
    setIsLoading(true);
    try {
      const newRun = await triggerScheduledAnalyze(activeTab);
      setRuns((prev) => {
        // Remove any old run for same period today if exists to keep it fresh
        const filtered = prev.filter(
          (r) => !(r.period === activeTab && r.timestamp.startsWith(newRun.timestamp.split("T")[0]))
        );
        return [...filtered, newRun];
      });
    } catch (exc) {
      alert(`Analysis failed: ${exc instanceof Error ? exc.message : exc}`);
    } finally {
      setIsLoading(false);
    }
  }

  // Simple renderer to format bullet points and headers from Markdown
  function renderContent(text: string) {
    if (!text) return null;
    return text.split("\n").map((line, idx) => {
      const cleanLine = line.trim();
      if (!cleanLine) return <div key={idx} className="h-1.5" />;
      
      if (cleanLine.startsWith("###")) {
        return (
          <h4 key={idx} className="text-sm font-bold text-zinc-900 mt-3 mb-1">
            {cleanLine.replace("###", "").trim()}
          </h4>
        );
      }
      if (cleanLine.startsWith("*") || cleanLine.startsWith("-")) {
        const content = cleanLine.substring(1).trim();
        return (
          <div key={idx} className="flex items-start gap-2 text-xs text-zinc-600 my-1 leading-relaxed pl-1">
            <span className="text-accent mt-1 select-none">•</span>
            <span>{parseInlineBold(content)}</span>
          </div>
        );
      }
      return (
        <p key={idx} className="text-xs text-zinc-600 leading-relaxed my-1">
          {parseInlineBold(cleanLine)}
        </p>
      );
    });
  }

  function parseInlineBold(text: string) {
    const parts = text.split("**");
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        return <strong key={i} className="font-bold text-zinc-800">{part}</strong>;
      }
      return part;
    });
  }

  const periodConfig = {
    morning: {
      label: "Morning Session",
      icon: <Sun size={14} className="text-amber-500" />,
      desc: "Pre-market cataloging, opening moves, and catalyst reviews."
    },
    midday: {
      label: "Midday Review",
      icon: <Sunset size={14} className="text-orange-500" />,
      desc: "Consolidation indicators, momentum verification, and holding reviews."
    },
    night: {
      label: "Night wrap-up",
      icon: <Moon size={14} className="text-indigo-400" />,
      desc: "Overall performance audit, drawdown review, and setups for tomorrow."
    }
  };

  return (
    <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="text-accent" size={18} />
          <div>
            <h3 className="text-sm font-bold text-zinc-900">Daily Tactical Action Suggestions</h3>
            <p className="text-[10px] text-zinc-400 font-medium">Session-based portfolio coaching & decision support</p>
          </div>
        </div>
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-zinc-50 px-2.5 py-1.5 text-xs font-bold text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 transition-colors focus:outline-none"
        >
          <RefreshCw size={12} className={isLoading ? "animate-spin text-accent" : "text-zinc-500"} />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="grid grid-cols-3 gap-1.5 bg-zinc-50 border border-line rounded-lg p-1">
        {(["morning", "midday", "night"] as const).map((tab) => {
          const isActive = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`inline-flex items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-bold transition-all focus:outline-none ${
                isActive
                  ? "bg-white text-zinc-900 shadow-sm border border-line"
                  : "text-zinc-500 hover:text-zinc-900"
              }`}
            >
              {periodConfig[tab].icon}
              {periodConfig[tab].label.split(" ")[0]}
            </button>
          );
        })}
      </div>

      {/* Content Panel */}
      <div className="mt-4 bg-zinc-50/50 border border-line rounded-lg p-4 min-h-[160px]">
        <div className="flex items-center gap-2 mb-3">
          {periodConfig[activeTab].icon}
          <div>
            <span className="text-xs font-bold text-zinc-800">{periodConfig[activeTab].label}</span>
            <p className="text-[9px] text-zinc-400 leading-tight mt-0.5">{periodConfig[activeTab].desc}</p>
          </div>
        </div>

        {activeRun ? (
          <div className="space-y-2.5">
            {renderContent(activeRun.analysis_text)}
            <div className="pt-2 text-[9px] text-zinc-400 font-semibold border-t border-line/60 flex items-center justify-between">
              <span>Timestamp: {new Date(activeRun.timestamp).toLocaleString()}</span>
              <span className="inline-flex items-center gap-0.5 text-accent">
                <CheckCircle size={10} /> Active Decision Support
              </span>
            </div>
          </div>
        ) : (
          <div className="h-[120px] flex flex-col items-center justify-center text-center">
            <p className="text-xs text-zinc-400 italic">No analysis generated for this session yet.</p>
            <button
              onClick={handleRefresh}
              className="mt-2.5 text-xs font-bold text-accent hover:underline flex items-center gap-1"
            >
              <RefreshCw size={11} /> Generate Analysis Now
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
