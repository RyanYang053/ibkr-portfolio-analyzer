import { Disclaimer } from "@/components/Disclaimer";
import { DecisionCenterClient } from "@/components/decision-center/DecisionCenterClient";
import { formatApiError, getDecisionCenter } from "@/lib/api";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ account_id?: string }>;
}

export default async function DecisionCenterPage(props: PageProps) {
  const searchParams = await props.searchParams;
  const accountId = searchParams.account_id || undefined;

  let payload: Record<string, unknown> | null = null;
  let loadError: string | null = null;
  try {
    payload = await getDecisionCenter(accountId);
  } catch (error) {
    loadError = formatApiError(error);
  }

  const holdings = Array.isArray(payload?.holdings)
    ? (payload?.holdings as Array<Record<string, unknown>>)
    : [];
  const methodologyStatus = String(payload?.methodology_status || "experimental");

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Decision support</p>
        <h2 className="text-3xl font-semibold">Decision Center</h2>
        <p className="mt-1 max-w-3xl text-sm text-zinc-600">
          Ordered deterministic gates and investor lenses for holding review. Valuation stays withheld.
        </p>
      </div>
      <Disclaimer />
      {loadError ? (
        <div className="rounded-md border border-warning bg-amber-50 p-4 text-sm text-warning">{loadError}</div>
      ) : (
        <DecisionCenterClient
          accountId={accountId}
          methodologyStatus={methodologyStatus}
          holdings={holdings.map((row) => ({
            instrument_key: String(row.instrument_key || row.symbol || ""),
            symbol: String(row.symbol || ""),
            action: String(row.action || ""),
            valuation_status: String(row.valuation_status || "withheld"),
          }))}
        />
      )}
    </div>
  );
}
