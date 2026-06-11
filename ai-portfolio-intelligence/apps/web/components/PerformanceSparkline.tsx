"use client";

type PerformanceSparklineProps = {
  values: number[];
  width?: number;
  height?: number;
  strokeColor?: string;
  fillColor?: string;
};

export function PerformanceSparkline({
  values,
  width = 300,
  height = 80,
  strokeColor = "hsl(221, 83%, 53%)", // Accent Blue
  fillColor = "rgba(59, 130, 246, 0.08)", // Transparent Blue
}: PerformanceSparklineProps) {
  if (values.length < 2) {
    return <div className="text-xs text-zinc-400">Not enough data to plot</div>;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min === 0 ? 1 : max - min;

  // Add small padding to avoid drawing right on the edges
  const paddingX = 4;
  const paddingY = 8;

  const points = values.map((val, index) => {
    const x = paddingX + (index / (values.length - 1)) * (width - 2 * paddingX);
    const y = paddingY + (1 - (val - min) / range) * (height - 2 * paddingY);
    return { x, y };
  });

  // Build path string for the line
  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");

  // Build path string for the filled area underneath
  const areaPath = `
    ${linePath}
    L ${points[points.length - 1].x.toFixed(1)} ${height}
    L ${points[0].x.toFixed(1)} ${height}
    Z
  `;

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} className="overflow-visible">
        <defs>
          <linearGradient id="sparklineGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={strokeColor} stopOpacity={0.15} />
            <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
          </linearGradient>
        </defs>

        {/* Filled Area */}
        <path d={areaPath} fill="url(#sparklineGrad)" />

        {/* Stroke Line */}
        <path
          d={linePath}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* End Pulse Point */}
        {points.length > 0 && (
          <g>
            <circle
              cx={points[points.length - 1].x}
              cy={points[points.length - 1].y}
              r="4.5"
              fill={strokeColor}
            />
            <circle
              cx={points[points.length - 1].x}
              cy={points[points.length - 1].y}
              r="8"
              fill="none"
              stroke={strokeColor}
              strokeWidth="1.5"
              className="animate-ping"
              style={{ transformOrigin: `${points[points.length - 1].x}px ${points[points.length - 1].y}px` }}
            />
          </g>
        )}
      </svg>
    </div>
  );
}
