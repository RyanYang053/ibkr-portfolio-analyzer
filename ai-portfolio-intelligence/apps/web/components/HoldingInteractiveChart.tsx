"use client";

import { useEffect, useState } from "react";
import { getChartData } from "@/lib/api";

type PriceData = {
  date: string;
  close: number;
  open: number;
  high: number;
  low: number;
};

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

  // Calculate scales
  const margin = { top: 15, right: 15, bottom: 25, left: 45 };
  const width = 500;
  const height = 180;

  const highs = data.map((d) => d.high);
  const lows = data.map((d) => d.low);

  const minVal = Math.min(...lows) * 0.99;
  const maxVal = Math.max(...highs) * 1.01;
  const valRange = maxVal - minVal;

  const getX = (index: number) => {
    return margin.left + (index / (data.length - 1)) * (width - margin.left - margin.right);
  };

  const getY = (val: number) => {
    return height - margin.bottom - ((val - minVal) / valRange) * (height - margin.top - margin.bottom);
  };

  // Build SVG Path for Line Chart
  const points = data.map((d, i) => `${getX(i)},${getY(d.close)}`).join(" ");
  const linePath = `M ${points}`;
  const areaPath = `${linePath} L ${getX(data.length - 1)},${height - margin.bottom} L ${getX(0)},${height - margin.bottom} Z`;

  // Colors
  const firstVal = data[0]?.close || 0;
  const lastVal = data[data.length - 1]?.close || 0;
  const isUpTrend = lastVal >= firstVal;
  const strokeColor = isUpTrend ? "#22c55e" : "#ef4444";
  const areaGradientId = `gradient-${symbol}-${range}`;

  const formatTickDate = (dateStr: string, rangeStr: string) => {
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr;
      if (rangeStr === "1D") {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      } else {
        return date.toLocaleDateString([], { timeZone: "UTC", month: "short", day: "numeric" });
      }
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="mt-4 border-t border-line pt-4">
      {/* Header Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 text-xs">
        {/* Timelines */}
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

        {/* Hover values or legend */}
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

        {/* Chart type select */}
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

      {/* SVG Canvas */}
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto overflow-visible select-none">
          <defs>
            <linearGradient id={areaGradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1={margin.left} y1={getY(minVal)} x2={width - margin.right} y2={getY(minVal)} stroke="#e4e4e7" strokeDasharray="3 3" />
          <line x1={margin.left} y1={getY((minVal + maxVal) / 2)} x2={width - margin.right} y2={getY((minVal + maxVal) / 2)} stroke="#e4e4e7" strokeDasharray="3 3" />
          <line x1={margin.left} y1={getY(maxVal)} x2={width - margin.right} y2={getY(maxVal)} stroke="#e4e4e7" strokeDasharray="3 3" />

          {/* Y-Axis Labels */}
          <text x={margin.left - 8} y={getY(minVal) + 4} textAnchor="end" className="text-[9px] fill-zinc-400 font-medium">${minVal.toFixed(1)}</text>
          <text x={margin.left - 8} y={getY((minVal + maxVal) / 2) + 4} textAnchor="end" className="text-[9px] fill-zinc-400 font-medium">${((minVal + maxVal) / 2).toFixed(1)}</text>
          <text x={margin.left - 8} y={getY(maxVal) + 4} textAnchor="end" className="text-[9px] fill-zinc-400 font-medium">${maxVal.toFixed(1)}</text>

          {/* Draw Line Chart */}
          {chartType === "line" && (
            <>
              <path d={areaPath} fill={`url(#${areaGradientId})`} />
              <path d={linePath} fill="none" stroke={strokeColor} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
              {/* Highlight End Dot */}
              <circle cx={getX(data.length - 1)} cy={getY(lastVal)} r={4} fill={strokeColor} stroke="#ffffff" strokeWidth={1.5} className="animate-pulse" />
            </>
          )}

          {/* Draw Candle Chart */}
          {chartType === "candle" && (() => {
            const slotWidth = (width - margin.left - margin.right) / data.length;
            const candleWidth = Math.max(2, slotWidth * 0.7);
            return data.map((d, i) => {
              const x = getX(i);
              const isUp = d.close >= d.open;
              const color = isUp ? "#22c55e" : "#ef4444";
              const yOpen = getY(d.open);
              const yClose = getY(d.close);
              const yHigh = getY(d.high);
              const yLow = getY(d.low);
              
              const yMinBody = Math.min(yOpen, yClose);
              const yMaxBody = Math.max(yOpen, yClose);
              const bodyHeight = Math.max(1.5, yMaxBody - yMinBody);

              return (
                <g key={i}>
                  {/* Shadow wick */}
                  <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth={1.2} />
                  {/* Candle Body */}
                  <rect
                    x={x - candleWidth / 2}
                    y={yMinBody}
                    width={candleWidth}
                    height={bodyHeight}
                    fill={color}
                  />
                </g>
              );
            });
          })()}

          {/* Hover interactive bars */}
          {data.map((d, i) => {
            const x = getX(i);
            const slotWidth = (width - margin.left - margin.right) / data.length;
            return (
              <rect
                key={`hover-${i}`}
                x={x - slotWidth / 2}
                y={margin.top}
                width={slotWidth}
                height={height - margin.top - margin.bottom}
                fill="transparent"
                onMouseEnter={() => setHoveredPoint(d)}
                onMouseLeave={() => setHoveredPoint(null)}
                className="cursor-pointer"
              />
            );
          })}

          {/* X-Axis dates */}
          {data.length > 1 && (
            <>
              <text x={margin.left} y={height - 8} textAnchor="start" className="text-[9px] fill-zinc-400 font-medium">
                {formatTickDate(data[0].date, range)}
              </text>
              <text x={width - margin.right} y={height - 8} textAnchor="end" className="text-[9px] fill-zinc-400 font-medium">
                {formatTickDate(data[data.length - 1].date, range)}
              </text>
            </>
          )}
        </svg>
      </div>
    </div>
  );
}
