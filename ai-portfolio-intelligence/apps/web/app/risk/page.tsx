import { AllocationBars } from "@/components/AllocationBars";
import { Disclaimer } from "@/components/Disclaimer";
import { StatCard } from "@/components/StatCard";
import { getRisk } from "@/lib/api";
import { RiskGauge } from "@/components/RiskGauge";
import { DonutChart } from "@/components/DonutChart";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ account_id?: string }>;
}

export default async function RiskPage(props: PageProps) {
  const searchParams = await props.searchParams;
  const accountId = searchParams.account_id || undefined;

  const risk = await getRisk(accountId);

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Risk monitoring</p>
        <h2 className="text-3xl font-semibold">Risk Center</h2>
      </div>
      <Disclaimer />
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1fr_1fr_1fr]">
        <RiskGauge score={risk.risk_score} label="Portfolio Risk Score" />
        <StatCard label="Top 5 Concentration" value={`${risk.top_5_concentration.toFixed(2)}%`} />
        <StatCard label="Herfindahl" value={risk.herfindahl_concentration_score.toFixed(4)} detail={risk.herfindahl_concentration_label} />
        <StatCard label="Speculative Basket" value={`${risk.speculative_percent.toFixed(2)}%`} tone="warn" />
        <StatCard label="Margin Usage" value={`${risk.margin_usage_percent.toFixed(2)}%`} />
      </section>
      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold">Sector Risk</h3>
          <DonutChart data={risk.sector_exposure} title="Sectors" />
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-4 text-lg font-semibold">Active Alerts</h3>
          <div className="grid gap-3">
            {risk.alerts.map((alert) => (
              <div key={alert.alert_type} className="rounded-md border border-line bg-panel p-3 text-sm">
                <div className="font-semibold">{alert.alert_type.replaceAll("_", " ")}</div>
                <p className="text-zinc-700">{alert.message}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
