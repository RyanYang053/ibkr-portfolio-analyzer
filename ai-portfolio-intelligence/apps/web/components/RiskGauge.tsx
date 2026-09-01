"use client";

type RiskGaugeProps = {
  score: number;
  label?: string;
};

export function RiskGauge({ score, label = "Risk Score" }: RiskGaugeProps) {
  // Clamp score between 0 and 100
  const normalizedScore = Math.max(0, Math.min(score, 100));
  
  // Dasharray length for a semi-circle with r=75 is: PI * r = 235.62
  const maxDash = 235.62;
  const dashOffset = maxDash - (maxDash * normalizedScore) / 100;
  
  // Angle for the needle: ranges from -90 degrees (at score=0) to +90 degrees (at score=100)
  const needleRotation = (normalizedScore / 100) * 180 - 90;

  // Determine color/description based on score levels
  let rating = "Low risk";
  let textColor = "text-positive";
  if (normalizedScore > 75) {
    rating = "Very high risk";
    textColor = "text-negative";
  } else if (normalizedScore > 50) {
    rating = "Elevated risk";
    textColor = "text-warning";
  } else if (normalizedScore > 25) {
    rating = "Moderate risk";
    textColor = "text-warning";
  }

  return (
    <div className="flex flex-col items-center rounded-lg border border-hairline bg-surface p-3 shadow-sm">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="relative h-[105px] w-[180px] overflow-hidden">
        <svg
          viewBox="0 0 200 110"
          width="100%"
          height="100%"
          role="img"
          aria-label={`${label}: ${normalizedScore.toFixed(1)} out of 100 — ${rating}`}
        >
          <defs>
            {/* Gradient for the gauge arc */}
            <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="hsl(142, 71%, 45%)" />   {/* Emerald */}
              <stop offset="40%" stopColor="hsl(38, 92%, 50%)" />    {/* Amber */}
              <stop offset="80%" stopColor="hsl(16, 92%, 50%)" />    {/* Orange */}
              <stop offset="100%" stopColor="hsl(346, 84%, 50%)" />  {/* Rose */}
            </linearGradient>
          </defs>

          {/* Background Arc */}
          <path
            d="M 25 95 A 75 75 0 0 1 175 95"
            fill="none"
            stroke="var(--c-3)"
            strokeWidth="14"
            strokeLinecap="round"
          />

          {/* Active Value Arc */}
          <path
            d="M 25 95 A 75 75 0 0 1 175 95"
            fill="none"
            stroke="url(#gaugeGradient)"
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={maxDash}
            strokeDashoffset={dashOffset}
            className="transition-all duration-1000 ease-out"
          />

          {/* Center Pivot Point */}
          <circle cx="100" cy="95" r="8" fill="var(--c-8)" />

          {/* Needle Pointer */}
          <line
            x1="100"
            y1="95"
            x2="100"
            y2="32"
            stroke="var(--c-8)"
            strokeWidth="3.5"
            strokeLinecap="round"
            style={{
              transform: `rotate(${needleRotation}deg)`,
              transformOrigin: "100px 95px",
            }}
            className="transition-transform duration-1000 ease-out"
          />
        </svg>
      </div>

      <div className="mt-1 flex flex-col items-center">
        <span className="num text-3xl font-bold text-zinc-900">{normalizedScore.toFixed(1)}</span>
        <span className={`text-xs font-semibold uppercase tracking-wider ${textColor} mt-0.5`}>
          {rating}
        </span>
      </div>
    </div>
  );
}
