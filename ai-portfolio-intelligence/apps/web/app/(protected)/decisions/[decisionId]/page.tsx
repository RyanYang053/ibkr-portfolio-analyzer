"use client";

import { use, useState } from "react";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getDecisionPacket, respondToDecision } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

export default function DecisionDetailPage({ params }: { params: Promise<{ decisionId: string }> }) {
  const { decisionId } = use(params);
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error, loading } = useClientResource(
    () => getDecisionPacket(decisionId),
    [decisionId, refreshKey],
  );

  if (loading) return <PageLoading />;
  if (error || !data) return <PageErrorBanner message={error ?? "Decision not found"} />;

  const packet = data as Record<string, unknown>;
  const gates = Array.isArray(packet.gates) ? (packet.gates as Array<Record<string, unknown>>) : [];
  const blockers = Array.isArray(packet.blockers) ? (packet.blockers as string[]) : [];
  const evidence = Array.isArray(packet.evidence)
    ? (packet.evidence as Array<Record<string, unknown>>)
    : [];
  const scenarios = Array.isArray(packet.scenarios)
    ? (packet.scenarios as Array<Record<string, unknown>>)
    : [];
  const responses = Array.isArray(packet.user_responses)
    ? (packet.user_responses as Array<Record<string, unknown>>)
    : [];

  async function onRespond(response: string) {
    await respondToDecision(decisionId, response);
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Decision packet</p>
        <h2 className="text-3xl font-semibold">{String(packet.symbol)}</h2>
        <p className="text-sm text-zinc-600">
          {String(packet.outcome)} · Priority {String(packet.priority ?? "routine")} · Confidence{" "}
          {String(packet.confidence_status ?? "provisional")}
        </p>
      </div>
      <Disclaimer />

      <section className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs uppercase text-zinc-500">Implementation</div>
          <div className="mt-1 font-semibold">{String(packet.implementation_status ?? "blocked")}</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs uppercase text-zinc-500">Order generated</div>
          <div className="mt-1 font-semibold">{packet.order_generated ? "yes" : "never"}</div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <div className="text-xs uppercase text-zinc-500">Gates failed</div>
          <div className="mt-1 font-semibold">{gates.filter((g) => !g.passed).length}</div>
        </div>
      </section>

      {blockers.length ? (
        <section className="rounded-md border border-line bg-amber-50 p-4 text-sm">
          <h3 className="mb-2 font-semibold">Blockers</h3>
          <ul className="list-disc pl-5">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="mb-3 font-semibold">Gates</h3>
        <ul className="grid gap-1 text-sm">
          {gates.map((g) => (
            <li key={String(g.gate_id || g.gate)} className="flex justify-between border-b border-line py-1">
              <span>{String(g.gate_id || g.gate)}</span>
              <span className={g.passed ? "text-emerald-700" : "text-amber-800"}>
                {g.passed ? "pass" : "fail"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="mb-3 font-semibold">Evidence</h3>
        {evidence.length === 0 ? (
          <p className="text-sm text-zinc-600">No evidence refs on this packet.</p>
        ) : (
          <ul className="grid gap-2 text-sm">
            {evidence.map((item) => (
              <li key={String(item.evidence_id)} className="border-b border-line py-2">
                <div className="font-medium">
                  {String(item.evidence_type)} · {String(item.quality_status || item.provider || "")}
                </div>
                <div className="text-xs text-zinc-600">
                  {String(item.evidence_id)}
                  {item.provisional ? " · provisional" : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-md border border-line bg-white p-4 overflow-x-auto">
        <h3 className="mb-3 font-semibold">Scenarios</h3>
        {scenarios.length === 0 ? (
          <p className="text-sm text-zinc-600">No scenarios on this packet.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-zinc-500">
                <th className="py-2 pr-3">Type</th>
                <th className="py-2 pr-3">Weight</th>
                <th className="py-2 pr-3">Ready</th>
                <th className="py-2">Blockers</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={String(s.scenario_id)} className="border-b border-line last:border-0">
                  <td className="py-2 pr-3">{String(s.scenario_type)}</td>
                  <td className="py-2 pr-3">{String(s.proposed_weight_percent ?? "—")}</td>
                  <td className="py-2 pr-3">{s.implementation_ready ? "yes" : "no"}</td>
                  <td className="py-2 text-amber-800">
                    {Array.isArray(s.blockers) ? (s.blockers as string[]).join(", ") || "—" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {responses.length ? (
        <section className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-2 font-semibold">Recorded responses</h3>
          <ul className="grid gap-1">
            {responses.map((row, idx) => (
              <li key={String(row.response_id || idx)}>
                {String(row.response || row.status || "response")} · {String(row.recorded_at || "")}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="flex flex-wrap gap-2">
        {["accepted_for_review", "deferred", "rejected", "no_action"].map((response) => (
          <button
            key={response}
            type="button"
            className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel"
            onClick={() => onRespond(response)}
          >
            {response.replaceAll("_", " ")}
          </button>
        ))}
      </section>

      <Link
        className="text-sm text-accent hover:underline"
        href={`/holdings/${encodeURIComponent(String(packet.instrument_key || ""))}`}
      >
        Open holding
      </Link>
    </div>
  );
}
