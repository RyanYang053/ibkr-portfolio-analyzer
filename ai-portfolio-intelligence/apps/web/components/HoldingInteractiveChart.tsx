"use client";

import { useEffect, useState } from "react";
import { getChartData } from "@/lib/api";
import { LightweightPriceChart, type PriceData } from "@/components/LightweightPriceChart";

export function HoldingInteractiveChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<"1D" | "1M" | "3M" | "1Y">("1Y");
  const [chartType, setChartType] = useState<"line" | "candle">("line");
  const [data, setData] = useState<PriceData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hoveredPoint, setHoveredPoint] = useState<PriceData | null>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    getChartData(symbol, range).then((prices) => {
      if (active) {
        setData(prices);
        setIsLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [symbol, range]);

  if (isLoading) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-zinc-400 border-t border-line mt-4">
        <span className="animate-pulse">Loading chart data...</span>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-zinc-400 border-t border-line mt-4">
        No price data available
      </div>
    );
  }

  return (
    <div className="mt-4 border-t border-line pt-4">
      {/* Header Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 text-xs">
        <div className="inline-flex rounded-md border border-line bg-panel p-0.5">
          {(["1D", "1M", "3M", "1Y"] as const).map((r) => (
            <button
              key={r}
              className={`px-2.5 py-1 rounded-sm font-medium transition-colors ${
                range === r
                  ? "bg-white text-zinc-900 shadow-sm border border-line/50"
                  : "text-zinc-500 hover:text-zinc-900"
              }`}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>

        {hoveredPoint ? (
          <div className="flex gap-2 text-[10px] text-zinc-600 bg-zinc-50 border border-line px-2 py-1 rounded font-mono">
            <span>O: <strong className="text-zinc-800">${hoveredPoint.open.toFixed(2)}</strong></span>
            <span>H: <strong className="text-zinc-800">${hoveredPoint.high.toFixed(2)}</strong></span>
            <span>L: <strong className="text-zinc-800">${hoveredPoint.low.toFixed(2)}</strong></span>
            <span>C: <strong className="text-zinc-800">${hoveredPoint.close.toFixed(2)}</strong></span>
          </div>
        ) : (
          <div className="text-[11px] text-zinc-400">Hover over chart to view values</div>
        )}

        <div className="inline-flex rounded-md border border-line bg-panel p-0.5">
          <button
            className={`px-2 py-1 rounded-sm font-medium transition-colors ${
              chartType === "line"
                ? "bg-white text-zinc-900 shadow-sm border border-line/50"
                : "text-zinc-500 hover:text-zinc-900"
            }`}
            onClick={() => setChartType("line")}
          >
            Line
          </button>
          <button
            className={`px-2 py-1 rounded-sm font-medium transition-colors ${
              chartType === "candle"
                ? "bg-white text-zinc-900 shadow-sm border border-line/50"
                : "text-zinc-500 hover:text-zinc-900"
            }`}
            onClick={() => setChartType("candle")}
          >
            Candle
          </button>
        </div>
      </div>

      <LightweightPriceChart data={data} chartType={chartType} onHover={setHoveredPoint} />
    </div>
  );
}
