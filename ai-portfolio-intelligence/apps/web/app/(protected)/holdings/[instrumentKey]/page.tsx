"use client";

import { use } from "react";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { ThesisEditor } from "@/components/decision-center/ThesisEditor";
import { OptionsStrategyDashboard } from "@/components/OptionsStrategyDashboard";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import {
  getHoldingDecision,
  getMonitoringEvents,
  getStockValuation,
  getTaxLots,
  respondToDecision,
  runTaxReconciliation,
} from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

const TABS = [
  "Decision",
  "Thesis",
  "Evidence",
  "Valuation",
  "Risk",
  "Tax lots",
  "Options",
  "Scenarios",
  "Monitoring",
  "History",
] as const;

function HoldingContent({ instrumentKey }: { instrumentKey: string }) {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const [tab, setTab] = useState<(typeof TABS)[number]>("Decision");
  const [responseNote, setResponseNote] = useState<string | null>(null);
  const { data, error, loading } = useClientResource(
    () => getHoldingDecision(instrumentKey, accountId),
    [instrumentKey, accountId],
  );

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const packet = (data || {}) as Record<string, unknown>;
  const gates = Array.isArray(packet.gates) ? (packet.gates as Array<Record<string, unknown>>) : [];
  const scenarios = Array.isArray(packet.scenarios)
    ? (packet.scenarios as Array<Record<string, unknown>>)
    : [];
  const evidence = Array.isArray(packet.evidence)
    ? (packet.evidence as Array<Record<string, unknown>>)
    : [];
  const blockers = Array.isArray(packet.blockers) ? (packet.blockers as string[]) : [];
  const decisionId = String(packet.decision_id || "");
  const thesis = (packet.thesis && typeof packet.thesis === "object"
    ? (packet.thesis as Record<string, unknown>)
    : {}) as Record<string, unknown>;
  const symbol = String(packet.symbol || instrumentKey.split(":")[0] || instrumentKey).toUpperCase();
  const conIdRaw = packet.con_id ?? (instrumentKey.includes(":") ? instrumentKey.split(":")[1] : null);
  const conId = conIdRaw != null && conIdRaw !== "" ? Number(conIdRaw) : null;

  async function onRespond(response: string) {
    if (!decisionId) return;
    await respondToDecision(decisionId, response, { reasoning: "Recorded from holding workspace" });
    setResponseNote(`Recorded response: ${response}`);
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Holding workspace</p>
        <h2 className="text-3xl font-semibold">{symbol}</h2>
        <p className="text-sm text-zinc-600">
          Outcome: {String(packet.outcome || packet.action || "—")}
          {packet.previous_outcome ? ` (was ${String(packet.previous_outcome)})` : ""}
          {" · "}Priority {String(packet.priority || "routine")}
          {" · "}Confidence {String(packet.confidence_status || "provisional")}
        </p>
      </div>
      <Disclaimer />

      <div className="flex flex-wrap gap-2 border-b border-line pb-2">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            className={`rounded-md px-3 py-1.5 text-sm ${
              tab === name ? "bg-panel font-semibold" : "text-zinc-600 hover:bg-panel"
            }`}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Decision" ? (
        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-md border border-line bg-white p-4 text-sm">
            <h3 className="mb-2 font-semibold">Current Decision Packet</h3>
            <div>Decision ID: {decisionId || "—"}</div>
            <div>Implementation: {String(packet.implementation_status || "blocked")}</div>
            <div>Valuation: {String(packet.valuation_status || "withheld")}</div>
            <div>Order generated: never</div>
            <div className="mt-2 text-amber-800">
              Blockers: {blockers.length ? blockers.join(", ") : "none"}
            </div>
          </div>
          <div className="rounded-md border border-line bg-white p-4 text-sm">
            <h3 className="mb-2 font-semibold">Record your response</h3>
            <div className="flex flex-wrap gap-2">
              {["accepted_for_review", "deferred", "no_action", "rejected"].map((r) => (
                <button
                  key={r}
                  type="button"
                  className="rounded-md border border-line px-2 py-1 hover:bg-panel"
                  onClick={() => onRespond(r)}
                  disabled={!decisionId}
                >
                  {r}
                </button>
              ))}
            </div>
            {responseNote ? <p className="mt-2 text-zinc-600">{responseNote}</p> : null}
          </div>
          <div className="md:col-span-2 rounded-md border border-line bg-white p-4">
            <h3 className="mb-2 font-semibold">Gate timeline</h3>
            <ul className="space-y-1 text-sm">
              {gates.map((gate, idx) => (
                <li key={`${gate.gate_id || gate.gate}-${idx}`}>
                  <span className="font-medium">{String(gate.gate_id || gate.gate)}</span>
                  {" — "}
                  {gate.passed ? "passed" : "failed"}
                  {Array.isArray(gate.blockers) && gate.blockers.length
                    ? ` (${(gate.blockers as string[]).join(", ")})`
                    : ""}
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {tab === "Evidence" ? (
        <section className="rounded-md border border-line bg-white p-4 text-sm">
          {evidence.length === 0 ? (
            <p>No evidence refs on this packet yet.</p>
          ) : (
            <ul className="space-y-2">
              {evidence.map((ev) => (
                <li key={String(ev.evidence_id)}>
                  <span className="font-medium">{String(ev.evidence_type)}</span> via {String(ev.provider)} ·{" "}
                  {String(ev.quality_status)} · sha {String(ev.content_sha256 || "").slice(0, 12)}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {tab === "Scenarios" ? (
        <section className="rounded-md border border-line bg-white p-4 text-sm">
          <table className="min-w-full text-left">
            <thead>
              <tr className="border-b border-line text-xs uppercase text-zinc-500">
                <th className="py-2">Type</th>
                <th className="py-2">Weight %</th>
                <th className="py-2">Ready</th>
                <th className="py-2">Blockers</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={String(s.scenario_id)} className="border-b border-line last:border-0">
                  <td className="py-2">{String(s.scenario_type)}</td>
                  <td className="py-2">{String(s.proposed_weight_percent ?? "—")}</td>
                  <td className="py-2">{s.implementation_ready ? "yes" : "no"}</td>
                  <td className="py-2 text-amber-800">
                    {Array.isArray(s.blockers) ? (s.blockers as string[]).join(", ") || "—" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {tab === "Valuation" ? (
        <ValuationPanel symbol={symbol} accountId={accountId} packetStatus={String(packet.valuation_status || "")} />
      ) : null}

      {tab === "History" ? (
        <HistoryPanel instrumentKey={instrumentKey} accountId={accountId} />
      ) : null}

      {tab === "Thesis" ? (
        <section className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-2 font-semibold">Thesis status (from Decision Packet)</h3>
          <p>Status: {String(packet.thesis_status || thesis.status || "unknown")}</p>
          <div className="mt-4">
            <ThesisEditor
              instrumentKey={instrumentKey}
              initialText={String(thesis.text || thesis.summary || thesis.thesis_text || "")}
              accountId={accountId}
            />
          </div>
        </section>
      ) : null}

      {tab === "Risk" ? (
        <section className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-2 font-semibold">Risk and policy gates</h3>
          <ul className="grid gap-1">
            {gates
              .filter(
                (g) =>
                  String(g.gate_id || "").includes("risk") ||
                  String(g.gate_id || "").includes("policy") ||
                  String(g.gate_id || "") === "portfolio_fit",
              )
              .map((g) => (
                <li key={String(g.gate_id)} className="flex justify-between border-b border-line py-1">
                  <span>{String(g.gate_id)}</span>
                  <span className={g.passed ? "text-emerald-700" : "text-amber-800"}>
                    {g.passed ? "pass" : "fail"}
                  </span>
                </li>
              ))}
          </ul>
          {!gates.some(
            (g) =>
              String(g.gate_id || "").includes("risk") ||
              String(g.gate_id || "") === "portfolio_fit",
          ) ? (
            <p className="text-zinc-600">No dedicated risk/policy gate rows on this packet.</p>
          ) : null}
        </section>
      ) : null}

      {tab === "Tax lots" ? (
        <TaxLotsPanel
          symbol={symbol}
          accountId={accountId}
          gates={gates}
        />
      ) : null}

      {tab === "Options" ? (
        <section className="grid gap-4">
          <div className="rounded-md border border-line bg-white p-4 text-sm">
            <p className="text-zinc-700">
              Options strategy views are evidence-only and never place or modify option orders.
            </p>
            <p className="mt-2 text-xs text-zinc-500">
              Reg T / broker-equivalent margin requirements remain withheld from this workspace. American
              exercise risk is not modeled here.
            </p>
            <Link
              className="mt-3 inline-block text-accent hover:underline"
              href={`/holdings/detail?symbol=${encodeURIComponent(symbol)}&tab=options`}
            >
              Open options evidence panel
            </Link>
          </div>
          <OptionsStrategyDashboard symbol={symbol} accountId={accountId} conId={conId} />
        </section>
      ) : null}

      {tab === "Monitoring" ? (
        <MonitoringPanel instrumentKey={instrumentKey} symbol={symbol} accountId={accountId} packet={packet} />
      ) : null}
    </div>
  );
}

function ValuationPanel({
  symbol,
  accountId,
  packetStatus,
}: {
  symbol: string;
  accountId?: string;
  packetStatus: string;
}) {
  const { data, error, loading } = useClientResource(
    () => getStockValuation(symbol, accountId),
    [symbol, accountId],
  );

  if (loading) return <p className="text-sm text-zinc-600">Loading valuation…</p>;
  if (error) {
    return (
      <section className="rounded-md border border-line bg-white p-4 text-sm">
        <p className="font-semibold">Valuation status: {packetStatus || "withheld"}</p>
        <p className="mt-2 text-amber-800">{error}</p>
        <p className="mt-2 text-zinc-600">
          Valuation is withheld or experimental until methodology approval for personal use. It cannot
          support Review Add while withheld.
        </p>
      </section>
    );
  }

  const fairLow = data?.fair_value_low;
  const fairMid = data?.fair_value_mid;
  const fairHigh = data?.fair_value_high;
  const status = String(data?.valuation_status || packetStatus || "unavailable");
  const methodology = String(data?.methodology || "—");

  return (
    <section className="rounded-md border border-line bg-white p-4 text-sm">
      <h3 className="mb-2 font-semibold">Scenario valuation</h3>
      <dl className="grid gap-2 md:grid-cols-2">
        <div>
          <span className="text-zinc-500">Status</span>
          <div className="font-medium">{status}</div>
        </div>
        <div>
          <span className="text-zinc-500">Methodology</span>
          <div className="font-medium">{methodology}</div>
        </div>
        <div>
          <span className="text-zinc-500">Fair value (low / mid / high)</span>
          <div className="font-medium">
            {fairLow != null || fairMid != null || fairHigh != null
              ? `${fairLow ?? "—"} / ${fairMid ?? "—"} / ${fairHigh ?? "—"}`
              : "Unavailable"}
          </div>
        </div>
        <div>
          <span className="text-zinc-500">Company type</span>
          <div className="font-medium">{String(data?.company_type || "—")}</div>
        </div>
      </dl>
      <p className="mt-3 text-xs text-zinc-500">
        Valuation may be approved_for_personal_use when golden fixtures pass. Review Add still requires
        Decision Packet gates.
      </p>
    </section>
  );
}

function TaxLotsPanel({
  symbol,
  accountId,
  gates,
}: {
  symbol: string;
  accountId?: string;
  gates: Array<Record<string, unknown>>;
}) {
  const [reconNote, setReconNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, error, loading } = useClientResource(() => getTaxLots(accountId), [accountId]);

  const lots = Array.isArray(data?.lots_open)
    ? (data.lots_open as Array<Record<string, unknown>>).filter(
        (lot) => String(lot.symbol || "").toUpperCase() === symbol.toUpperCase(),
      )
    : [];

  async function onReconcile() {
    setBusy(true);
    setReconNote(null);
    try {
      const result = await runTaxReconciliation(accountId);
      // P0.6: run_id and status live in the nested `run` object, not the top level.
      const run = (result.run ?? {}) as Record<string, unknown>;
      const runId = String(run.run_id ?? "unknown");
      const status = String(run.status ?? "unknown");
      setReconNote(
        `Reconciliation run ${runId} · status ${status} · order generated: never`,
      );
    } catch (err) {
      setReconNote(err instanceof Error ? err.message : "Reconciliation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-md border border-line bg-white p-4 text-sm">
      <h3 className="mb-2 font-semibold">Tax gate</h3>
      {gates
        .filter((g) => String(g.gate_id || "") === "tax")
        .map((g) => (
          <div key={String(g.gate_id)}>
            <p>Status: {g.passed ? "pass" : "fail"}</p>
            <p className="mt-1 text-zinc-600">
              {Array.isArray(g.blockers) ? (g.blockers as string[]).join(", ") || "No tax blockers" : "—"}
            </p>
          </div>
        ))}
      {!gates.some((g) => String(g.gate_id || "") === "tax") ? (
        <p className="text-zinc-600">Tax gate not present on this packet.</p>
      ) : null}

      <div className="mt-4 flex items-center justify-between gap-3">
        <h3 className="font-semibold">Open lots ({symbol})</h3>
        <button
          type="button"
          className="rounded-md border border-line px-2 py-1 text-xs hover:bg-panel disabled:opacity-50"
          onClick={onReconcile}
          disabled={busy}
        >
          {busy ? "Running…" : "Run tax reconciliation"}
        </button>
      </div>
      {reconNote ? <p className="mt-2 text-xs text-zinc-600">{reconNote}</p> : null}
      {loading ? <p className="mt-2 text-zinc-600">Loading tax lots…</p> : null}
      {error ? <p className="mt-2 text-amber-800">{error}</p> : null}
      {!loading && !error ? (
        lots.length === 0 ? (
          <p className="mt-2 text-zinc-600">No open lots for {symbol}.</p>
        ) : (
          <table className="mt-2 min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase text-zinc-500">
                <th className="py-2">Acquired</th>
                <th className="py-2">Qty</th>
                <th className="py-2">Cost / share</th>
                <th className="py-2">Currency</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot, idx) => (
                <tr key={`${lot.acquired_date}-${idx}`} className="border-b border-line last:border-0">
                  <td className="py-2">{String(lot.acquired_date || "—")}</td>
                  <td className="py-2">{String(lot.quantity ?? "—")}</td>
                  <td className="py-2">{String(lot.cost_basis_per_share ?? "—")}</td>
                  <td className="py-2">{String(lot.currency || "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : null}
      <p className="mt-3 text-xs text-zinc-500">
        Tax outputs remain experimental decision support unless broker-reconciled.
      </p>
    </section>
  );
}

function MonitoringPanel({
  instrumentKey,
  symbol,
  accountId,
  packet,
}: {
  instrumentKey: string;
  symbol: string;
  accountId?: string;
  packet: Record<string, unknown>;
}) {
  const { data, error, loading } = useClientResource(
    () => getMonitoringEvents(accountId),
    [accountId],
  );

  const events = Array.isArray(data?.events)
    ? (data.events as Array<Record<string, unknown>>).filter((event) => {
        const key = String(event.instrument_key || "").toUpperCase();
        const eventSymbol = String(event.symbol || "").toUpperCase();
        const targetKey = instrumentKey.toUpperCase();
        const targetSymbol = symbol.toUpperCase();
        return (
          key === targetKey ||
          key === targetSymbol ||
          key.startsWith(`${targetSymbol}:`) ||
          eventSymbol === targetSymbol
        );
      })
    : [];

  return (
    <section className="rounded-md border border-line bg-white p-4 text-sm">
      <p className="text-zinc-700">
        Monitoring alerts and snooze/ack live in the Monitoring inbox. This holding inherits Decision
        Packet blockers and change codes.
      </p>
      <p className="mt-2">
        Change codes:{" "}
        {Array.isArray(packet.change_reason_codes)
          ? (packet.change_reason_codes as string[]).join(", ") || "none"
          : "none"}
      </p>
      {loading ? <p className="mt-3 text-zinc-600">Loading monitoring events…</p> : null}
      {error ? <p className="mt-3 text-amber-800">{error}</p> : null}
      {!loading && !error ? (
        events.length === 0 ? (
          <p className="mt-3 text-zinc-600">No monitoring events for this instrument.</p>
        ) : (
          <ul className="mt-3 grid gap-2">
            {events.slice(0, 20).map((event, idx) => (
              <li key={String(event.event_id || idx)} className="border-b border-line py-2">
                <div className="font-medium">{String(event.rule_type || event.type || "event")}</div>
                <div className="text-xs text-zinc-600">
                  {String(event.message || "")} · status {String(event.status || "open")}
                </div>
              </li>
            ))}
          </ul>
        )
      ) : null}
      <Link className="mt-3 inline-block text-accent hover:underline" href="/monitoring">
        Open monitoring inbox
      </Link>
    </section>
  );
}

function HistoryPanel({
  instrumentKey,
  accountId,
}: {
  instrumentKey: string;
  accountId?: string;
}) {
  const { data, error, loading } = useClientResource(async () => {
    const { requireJson } = await import("@/lib/api");
    const query = accountId ? `?account_id=${accountId}` : "";
    return requireJson<Record<string, unknown>>(
      `/decisions/history/${encodeURIComponent(instrumentKey)}${query}`,
    );
  }, [instrumentKey, accountId]);

  if (loading) return <p className="text-sm text-zinc-600">Loading history…</p>;
  if (error) return <p className="text-sm text-amber-800">{error}</p>;
  const history = Array.isArray(data?.history) ? (data.history as Array<Record<string, unknown>>) : [];
  const observations = Array.isArray(data?.observations)
    ? (data.observations as Array<Record<string, unknown>>)
    : [];
  return (
    <section className="grid gap-4 md:grid-cols-2">
      <div className="rounded-md border border-line bg-white p-4 text-sm">
        <h3 className="mb-2 font-semibold">Outcome transitions</h3>
        {history.length === 0 ? (
          <p className="text-zinc-600">No recorded transitions yet.</p>
        ) : (
          <ul className="grid gap-2">
            {history.map((row, idx) => (
              <li key={String(row.decision_id || idx)} className="border-b border-line py-2">
                {String(row.previous_outcome || "—")} → {String(row.outcome)} ·{" "}
                {String(row.recorded_at || "")}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-md border border-line bg-white p-4 text-sm">
        <h3 className="mb-2 font-semibold">Observation windows</h3>
        {observations.length === 0 ? (
          <p className="text-zinc-600">No scheduled observation windows.</p>
        ) : (
          <ul className="grid gap-2">
            {observations.map((row) => (
              <li key={String(row.observation_id)} className="border-b border-line py-2">
                {String(row.window_days)}d · {String(row.status)} · due {String(row.due_at || "")}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function HoldingByKeyPage({ params }: { params: Promise<{ instrumentKey: string }> }) {
  const { instrumentKey } = use(params);
  return (
    <Suspense fallback={<PageLoading />}>
      <HoldingContent instrumentKey={decodeURIComponent(instrumentKey)} />
    </Suspense>
  );
}
