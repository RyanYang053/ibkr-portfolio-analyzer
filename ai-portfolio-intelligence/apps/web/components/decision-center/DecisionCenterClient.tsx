"use client";

import { useMemo, useState } from "react";
import { DecisionDrawer } from "@/components/decision-center/DecisionDrawer";
import { DecisionMatrix } from "@/components/decision-center/DecisionMatrix";
import { MethodologyBanner } from "@/components/decision-center/MethodologyBanner";
import { getHoldingLenses } from "@/lib/api";

type HoldingRow = {
  instrument_key?: string;
  symbol?: string;
  action?: string;
  valuation_status?: string;
};

export function DecisionCenterClient({
  holdings,
  accountId,
  methodologyStatus = "experimental",
}: {
  holdings: HoldingRow[];
  accountId?: string;
  methodologyStatus?: string;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [lenses, setLenses] = useState<Array<{ lens_id?: string; score?: number | null; status?: string }>>([]);

  const selectedRow = useMemo(
    () => holdings.find((row) => (row.instrument_key || row.symbol) === selected),
    [holdings, selected],
  );

  async function onSelect(instrumentKey: string) {
    setSelected(instrumentKey);
    try {
      const payload = await getHoldingLenses(instrumentKey, accountId);
      const rows = Array.isArray(payload.lenses) ? (payload.lenses as typeof lenses) : [];
      setLenses(rows);
    } catch {
      setLenses([]);
    }
  }

  return (
    <div className="grid gap-4">
      <MethodologyBanner status={methodologyStatus} />
      <DecisionMatrix holdings={holdings} onSelect={onSelect} />
      <DecisionDrawer
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        symbol={selectedRow?.symbol}
        instrumentKey={selected || undefined}
        action={selectedRow?.action}
        lenses={lenses}
        accountId={accountId}
      />
    </div>
  );
}
