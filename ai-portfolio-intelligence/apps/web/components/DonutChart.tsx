"use client";

import { useState } from "react";

type DonutChartProps = {
  data: Record<string, number>;
  title?: string;
};

// Sleek curated HSL colors for charts
const COLORS = [
  "hsl(221, 83%, 53%)", // Accent Blue
  "hsl(142, 71%, 45%)", // Emerald Green
  "hsl(262, 83%, 58%)", // Violet
  "hsl(38, 92%, 50%)",  // Amber
  "hsl(346, 84%, 50%)", // Rose
  "hsl(199, 89%, 48%)", // Sky Blue
  "hsl(16, 92%, 50%)",  // Orange
  "hsl(240, 5%, 65%)",  // Slate
];

export function DonutChart({ data, title = "Allocation" }: DonutChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Clean data: filter zero values and sort descending
  const entries = Object.entries(data)
    .filter(([, val]) => val > 0)
    .sort((a, b) => {
      if (b[1] !== a[1]) {
        return b[1] - a[1];
      }
      return a[0].localeCompare(b[0]);
    });

  const total = entries.reduce((sum, [, val]) => sum + val, 0);

  if (total === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-zinc-400">
        No allocation data available
      </div>
    );
  }

  // Trigonometry helpers to calculate path coordinates
  const getCoordinatesForPercent = (percent: number) => {
    const x = Math.cos(2 * Math.PI * percent);
    const y = Math.sin(2 * Math.PI * percent);
    return [x, y];
  };

  let accumulatedPercent = 0;
  const slices = entries.map(([label, value], index) => {
    const percent = value / total;
    const startPercent = accumulatedPercent;
    accumulatedPercent += percent;

    const [startX, startY] = getCoordinatesForPercent(startPercent);
    const [endX, endY] = getCoordinatesForPercent(accumulatedPercent);

    const largeArcFlag = percent > 0.5 ? 1 : 0;

    // Radii: outer = 90, inner = 60
    const rOut = 90;
    const rIn = 60;
    const cx = 100;
    const cy = 100;

    const x1Out = cx + startX * rOut;
    const y1Out = cy + startY * rOut;
    const x2Out = cx + endX * rOut;
    const y2Out = cy + endY * rOut;

    const x1In = cx + startX * rIn;
    const y1In = cy + startY * rIn;
    const x2In = cx + endX * rIn;
    const y2In = cy + endY * rIn;

    // Command: Move outer start -> Arc outer end -> Line inner end -> Arc inner start -> Close
    const pathData = percent >= 0.999
      ? `M ${cx} ${cy - rOut} A ${rOut} ${rOut} 0 1 1 ${cx - 0.01} ${cy - rOut} Z M ${cx} ${cy - rIn} A ${rIn} ${rIn} 0 1 1 ${cx - 0.01} ${cy - rIn} Z`
      : `M ${x1Out} ${y1Out} A ${rOut} ${rOut} 0 ${largeArcFlag} 1 ${x2Out} ${y2Out} L ${x2In} ${y2In} A ${rIn} ${rIn} 0 ${largeArcFlag} 0 ${x1In} ${y1In} Z`;

    const color = COLORS[index % COLORS.length];

    return {
      label,
      value,
      percent,
      pathData,
      color,
    };
  });

  return (
    <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
      {/* SVG Donut */}
      <div className="relative mx-auto h-[200px] w-[200px] shrink-0">
        <svg className="-rotate-90" viewBox="0 0 200 200" width="100%" height="100%">
          <g>
            {slices.map((slice, index) => {
              const isHovered = hoveredIndex === index;
              return (
                <path
                  key={slice.label}
                  d={slice.pathData}
                  fill={slice.color}
                  className="transition-all duration-200 cursor-pointer hover:opacity-90"
                  style={{
                    transform: isHovered ? "scale(1.03)" : "scale(1)",
                    transformOrigin: "100px 100px",
                  }}
                  onMouseEnter={() => setHoveredIndex(index)}
                  onMouseLeave={() => setHoveredIndex(null)}
                />
              );
            })}
          </g>
        </svg>

        {/* Center label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-xs uppercase tracking-wider text-zinc-400 font-medium">
            {hoveredIndex !== null ? slices[hoveredIndex].label : title}
          </span>
          <span className="text-xl font-semibold text-zinc-800">
            {hoveredIndex !== null
              ? `${slices[hoveredIndex].value.toFixed(1)}%`
              : `${total.toFixed(0)}%`}
          </span>
        </div>
      </div>

      {/* Legends */}
      <div className="flex-1 grid gap-2 max-h-[220px] overflow-y-auto pr-1">
        {slices.map((slice, index) => {
          const isHovered = hoveredIndex === index;
          return (
            <div
              key={slice.label}
              className={`flex items-center justify-between rounded-md p-1.5 transition-colors text-sm ${
                isHovered ? "bg-panel" : ""
              }`}
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: slice.color }}
                />
                <span className="truncate font-medium text-zinc-700">{slice.label}</span>
              </div>
              <span className="font-semibold text-zinc-900 ml-2">
                {slice.value.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
