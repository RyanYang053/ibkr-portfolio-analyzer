"use client";

import { useState } from "react";
import { TrendingUp, TrendingDown, DollarSign } from "lucide-react";

interface PnLEntry {
  date: string;
  timestamp: string;
  net_liquidation: number;
  cash: number;
  buying_power: number;
  margin_requirement: number;
  daily_pnl: number;
  daily_pnl_percent: number;
  positions: any[];
}

interface AIPnlChartProps {
  history: PnLEntry[];
}

export function AIPnlChart({ history }: AIPnlChartProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (!history || history.length === 0) {
    return (
      <div className="rounded-xl border border-line bg-white p-6 text-center text-zinc-400">
        No performance history logs found.
      </div>
    );
  }

  // 1. Calculate values for SVG scaling
  const netLiqValues = history.map((h) => h.net_liquidation);
  const minNetLiq = Math.min(...netLiqValues);
  const maxNetLiq = Math.max(...netLiqValues);
  const rangeNetLiq = maxNetLiq - minNetLiq || 1;

  // Add 10% padding to bounds
  const yMin = minNetLiq - rangeNetLiq * 0.15;
  const yMax = maxNetLiq + rangeNetLiq * 0.15;
  const yRange = yMax - yMin || 1;

  const width = 600;
  const height = 180;
  const paddingLeft = 60;
  const paddingRight = 20;
  const paddingTop = 15;
  const paddingBottom = 25;

  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;

  // Generate coordinates
  const points = history.map((entry, idx) => {
    const x = paddingLeft + (idx / (history.length - 1 || 1)) * chartWidth;
    const y = paddingTop + chartHeight - ((entry.net_liquidation - yMin) / yRange) * chartHeight;
    return { x, y, ...entry };
  });

  // Build SVG Path
  const linePath = points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = points.length > 0
    ? `${linePath} L ${points[points.length - 1].x} ${paddingTop + chartHeight} L ${points[0].x} ${paddingTop + chartHeight} Z`
    : "";

  const latest = history[history.length - 1];
  const first = history[0];
  const overallPnL = latest.net_liquidation - first.net_liquidation;
  const overallPnLPct = (overallPnL / (first.net_liquidation || 1)) * 100;
  const isUp = overallPnL >= 0;

  // Current hovered item details
  const hovered = hoveredIdx !== null ? points[hoveredIdx] : points[points.length - 1];

  return (
    <div className="rounded-xl border border-line bg-white p-5 shadow-sm transition-all hover:shadow-md">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-4">
        <div>
          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest block">
            Portfolio Performance History
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <h3 className="text-2xl font-bold text-zinc-900">
              ${hovered.net_liquidation.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </h3>
            <span
              className={`inline-flex items-center gap-0.5 text-xs font-bold px-1.5 py-0.5 rounded ${
                hovered.daily_pnl >= 0 ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-600"
              }`}
            >
              {hovered.daily_pnl >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
              {hovered.daily_pnl_percent >= 0 ? "+" : ""}
              {hovered.daily_pnl_percent.toFixed(2)}%
            </span>
          </div>
          <span className="text-[10px] text-zinc-400 font-medium">
            {hoveredIdx !== null ? `Snapshot Date: ${hovered.date}` : "Live Overview"}
          </span>
        </div>

        <div className="flex gap-4 border-l border-zinc-100 pl-4">
          <div>
            <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wide block">14D Net Change</span>
            <span className={`text-sm font-bold block mt-0.5 ${isUp ? "text-emerald-600" : "text-rose-600"}`}>
              {isUp ? "+" : ""}
              ${overallPnL.toLocaleString(undefined, { maximumFractionDigits: 0 })} ({overallPnLPct.toFixed(2)}%)
            </span>
          </div>
          <div>
            <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wide block">Current Cash</span>
            <span className="text-sm font-bold text-zinc-800 block mt-0.5">
              ${latest.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </div>
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full overflow-visible">
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-accent, #3b82f6)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--color-accent, #3b82f6)" stopOpacity="0.00" />
            </linearGradient>
            <linearGradient id="pnlUpGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.3" />
            </linearGradient>
            <linearGradient id="pnlDownGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#ef4444" stopOpacity="0.3" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line
            x1={paddingLeft}
            y1={paddingTop}
            x2={width - paddingRight}
            y2={paddingTop}
            stroke="#f4f4f5"
            strokeWidth="1"
          />
          <line
            x1={paddingLeft}
            y1={paddingTop + chartHeight / 2}
            x2={width - paddingRight}
            y2={paddingTop + chartHeight / 2}
            stroke="#f4f4f5"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
          <line
            x1={paddingLeft}
            y1={paddingTop + chartHeight}
            x2={width - paddingRight}
            y2={paddingTop + chartHeight}
            stroke="#e4e4e7"
            strokeWidth="1"
          />

          {/* Left Y Axis Labels */}
          <text
            x={paddingLeft - 10}
            y={paddingTop + 4}
            textAnchor="end"
            fontSize="8"
            fontWeight="bold"
            fill="#a1a1aa"
          >
            ${maxNetLiq.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </text>
          <text
            x={paddingLeft - 10}
            y={paddingTop + chartHeight / 2 + 3}
            textAnchor="end"
            fontSize="8"
            fontWeight="bold"
            fill="#a1a1aa"
          >
            ${((maxNetLiq + minNetLiq) / 2).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </text>
          <text
            x={paddingLeft - 10}
            y={paddingTop + chartHeight + 2}
            textAnchor="end"
            fontSize="8"
            fontWeight="bold"
            fill="#a1a1aa"
          >
            ${minNetLiq.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </text>

          {/* Bottom X Axis Labels (Dates) */}
          {history.length > 0 && (
            <>
              <text
                x={points[0].x}
                y={paddingTop + chartHeight + 16}
                textAnchor="start"
                fontSize="8"
                fontWeight="bold"
                fill="#a1a1aa"
              >
                {points[0].date}
              </text>
              <text
                x={points[Math.floor(points.length / 2)].x}
                y={paddingTop + chartHeight + 16}
                textAnchor="middle"
                fontSize="8"
                fontWeight="bold"
                fill="#a1a1aa"
              >
                {points[Math.floor(points.length / 2)].date}
              </text>
              <text
                x={points[points.length - 1].x}
                y={paddingTop + chartHeight + 16}
                textAnchor="end"
                fontSize="8"
                fontWeight="bold"
                fill="#a1a1aa"
              >
                {points[points.length - 1].date}
              </text>
            </>
          )}

          {/* Shaded Area */}
          <path d={areaPath} fill="url(#areaGrad)" />

          {/* Trend Line */}
          <path
            d={linePath}
            fill="none"
            stroke="var(--color-accent, #3b82f6)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Active Hover Points and Bars */}
          {points.map((p, idx) => {
            const isHovered = idx === hoveredIdx;
            return (
              <g key={idx}>
                {/* Vertical helper line on hover */}
                {isHovered && (
                  <line
                    x1={p.x}
                    y1={paddingTop}
                    x2={p.x}
                    y2={paddingTop + chartHeight}
                    stroke="var(--color-accent, #3b82f6)"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />
                )}

                {/* Plot line circles */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={isHovered ? 5 : 2}
                  fill={isHovered ? "var(--color-accent, #3b82f6)" : "white"}
                  stroke="var(--color-accent, #3b82f6)"
                  strokeWidth={isHovered ? 2 : 1.5}
                  className="transition-all duration-100"
                />

                {/* Hotspot triggers */}
                <rect
                  x={p.x - chartWidth / (history.length * 2)}
                  y={paddingTop}
                  width={chartWidth / history.length}
                  height={chartHeight}
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredIdx(idx)}
                  onMouseLeave={() => setHoveredIdx(null)}
                />
              </g>
            );
          })}
        </svg>
      </div>

      {/* Position performance breakdown preview for the hovered date */}
      {hovered && hovered.positions && hovered.positions.length > 0 && (
        <div className="mt-4 pt-3.5 border-t border-zinc-100">
          <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wide block mb-2">
            Top Performance Contributors ({hovered.date})
          </span>
          <div className="flex flex-wrap gap-2">
            {hovered.positions
              .filter((p: any) => Math.abs(p.daily_pnl) > 0)
              .slice(0, 5)
              .map((pos: any) => (
                <div
                  key={pos.symbol}
                  className="inline-flex items-center gap-1.5 rounded bg-zinc-50 border border-zinc-100 px-2 py-1 text-[10px] font-semibold text-zinc-700"
                >
                  <span className="font-bold text-zinc-900">{pos.symbol}</span>
                  <span
                    className={pos.daily_pnl >= 0 ? "text-emerald-600" : "text-rose-600"}
                  >
                    {pos.daily_pnl >= 0 ? "+" : ""}
                    {pos.daily_pnl_percent.toFixed(1)}%
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
