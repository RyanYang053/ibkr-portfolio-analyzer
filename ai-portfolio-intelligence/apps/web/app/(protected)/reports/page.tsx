"use client";

import { useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { AIPortfolioRefreshPanel } from "@/components/AIPortfolioRefreshPanel";
import { AIPnlChart } from "@/components/AIPnlChart";
import { DailyActionsPanel } from "@/components/DailyActionsPanel";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getMonthlyReview, getPnlHistory, getReports, getScheduleSettings } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

function MonthlyReviewPanel() {
  const [review, setReview] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const sections = ["performance", "risk", "allocation", "trade_process_analytics", "tax_activity", "goal_progress"];

  return (
    <section className="rounded-md border border-line bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Monthly investment review</h3>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setErr(null);
            try {
              setReview(await getMonthlyReview());
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Failed");
            } finally {
              setBusy(false);
            }
          }}
          className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50"
        >
          {busy ? "Generating…" : "Generate"}
        </button>
      </div>
      {err ? <div className="mt-3"><DegradedStateBanner message={err} /></div> : null}
      {review ? (
        <div className="mt-3 grid gap-2 text-sm">
          {sections.map((key) => {
            const sec = (review[key] ?? {}) as Record<string, unknown>;
            const status = String(sec.status ?? "unknown");
            return (
              <div key={key} className="rounded-md border border-line p-3">
                <div className="flex justify-between">
                  <span className="font-medium capitalize">{key.replaceAll("_", " ")}</span>
                  <span className={status === "available" ? "text-emerald-700" : "text-amber-700"}>{status}</span>
                </div>
                {status !== "available" ? (
                  <p className="text-xs text-zinc-600">{String(sec.note ?? "withheld — not fabricated")}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-3 text-sm text-zinc-600">
          Assembled from performance, risk, allocation, and journal process analytics. Unavailable
          sections are withheld, never fabricated.
        </p>
      )}
    </section>
  );
}

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

      <MonthlyReviewPanel />

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
