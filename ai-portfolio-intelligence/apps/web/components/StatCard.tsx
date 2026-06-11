type StatCardProps = {
  label: string;
  value: string;
  detail?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
};

const tones = {
  neutral: "border-line",
  good: "border-accent",
  warn: "border-warning",
  bad: "border-danger"
};

export function StatCard({ label, value, detail, tone = "neutral" }: StatCardProps) {
  return (
    <div className={`rounded-md border ${tones[tone]} bg-white p-4`}>
      <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      {detail ? <div className="mt-1 text-sm text-zinc-600">{detail}</div> : null}
    </div>
  );
}
