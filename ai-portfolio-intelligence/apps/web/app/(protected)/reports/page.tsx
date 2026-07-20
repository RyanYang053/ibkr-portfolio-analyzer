"use client";

import { Disclaimer } from "@/components/Disclaimer";
import { AIPortfolioRefreshPanel } from "@/components/AIPortfolioRefreshPanel";
import { AIPnlChart } from "@/components/AIPnlChart";
import { DailyActionsPanel } from "@/components/DailyActionsPanel";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getPnlHistory, getReports, getScheduleSettings } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

type ReportRow = {
  report_type: string;
  title: string;
  report_markdown: string;
  confidence: string;
  disclaimer: string;
  report_json: unknown;
};

export default function ReportsPage() {
  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getReports() as Promise<ReportRow[]>,
        getPnlHistory(),
        getScheduleSettings(),
      ]),
    [],
  );

  if (loading) {
    return <PageLoading />;
  }

  const [reports, pnlHistory, scheduleData] = data ?? [[], [], { runs: [] }];
  const aiPortfolioReport = reports.find((report) => report.report_type === "ai_portfolio");
  const otherReports = reports.filter((report) => report.report_type !== "ai_portfolio");
  const initialReport = aiPortfolioReport ? aiPortfolioReport.report_json : null;

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Structured research output</p>
        <h2 className="text-3xl font-semibold">Reports</h2>
      </div>
      <Disclaimer />
      {error ? <PageErrorBanner message={error} /> : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <AIPnlChart history={pnlHistory} />
        <DailyActionsPanel initialRuns={scheduleData.runs ?? []} />
      </section>

      <AIPortfolioRefreshPanel initialReport={initialReport} />

      <div className="grid gap-4">
        {otherReports.map((report, index) => (
          <article key={`${report.title}-${index}`} className="rounded-md border border-line bg-white p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">{report.title}</h3>
              <span className="text-sm text-zinc-600">Confidence: {report.confidence}</span>
            </div>
            <pre className="mt-3 whitespace-pre-wrap rounded-md bg-panel p-3 text-sm font-sans">{report.report_markdown}</pre>
            <p className="mt-3 text-xs text-zinc-600">{report.disclaimer}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
