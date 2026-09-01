/**
 * Presentation helpers for financial values and backend enum codes.
 *
 * Two rules the whole UI follows:
 *  1. A value the backend could not produce renders as an em dash, never as 0.
 *     Zero is a real number in a portfolio; "no data" must not look like it.
 *  2. Backend codes are snake_case (`review_trim`, `attention_required`).
 *     They are identifiers, not copy, so they are humanised before display.
 */

const MISSING = "—";

function isMissing(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (typeof value === "number" && !Number.isFinite(value))
  );
}

function toNumber(value: unknown): number | null {
  if (isMissing(value)) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** `$185,673.00`. Pass `compact` for `$185.7K` in tight stat tiles. */
export function formatCurrency(
  value: unknown,
  options: { currency?: string; decimals?: number; compact?: boolean; signed?: boolean } = {},
): string {
  const amount = toNumber(value);
  if (amount === null) return MISSING;
  const { currency = "USD", compact = false, signed = false } = options;
  const decimals = options.decimals ?? (compact ? 1 : 2);

  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    notation: compact ? "compact" : "standard",
    minimumFractionDigits: compact ? 0 : decimals,
    maximumFractionDigits: decimals,
  }).format(Math.abs(amount));

  const sign = amount < 0 ? "−" : signed && amount > 0 ? "+" : "";
  return `${sign}${formatted}`;
}

/** `12.49%`. `value` is already in percent units (12.49), not a ratio. */
export function formatPercent(
  value: unknown,
  options: { decimals?: number; signed?: boolean } = {},
): string {
  const amount = toNumber(value);
  if (amount === null) return MISSING;
  const { decimals = 2, signed = false } = options;
  const sign = amount < 0 ? "−" : signed && amount > 0 ? "+" : "";
  return `${sign}${Math.abs(amount).toFixed(decimals)}%`;
}

/** `12.49%` from a 0–1 ratio. */
export function formatRatioAsPercent(value: unknown, decimals = 1): string {
  const amount = toNumber(value);
  if (amount === null) return MISSING;
  return `${(amount * 100).toFixed(decimals)}%`;
}

/** Plain number with grouping, e.g. `1,204`. */
export function formatNumber(value: unknown, decimals?: number): string {
  const amount = toNumber(value);
  if (amount === null) return MISSING;
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals ?? 4,
  }).format(amount);
}

/** Sign of a P&L figure, for colour-coding. `null` when the value is missing. */
export function signOf(value: unknown): "positive" | "negative" | "flat" | null {
  const amount = toNumber(value);
  if (amount === null) return null;
  if (amount > 0) return "positive";
  if (amount < 0) return "negative";
  return "flat";
}

/** Tailwind text colour for a P&L figure. Neutral when the value is missing. */
export function toneClass(value: unknown): string {
  const sign = signOf(value);
  if (sign === "positive") return "text-positive";
  if (sign === "negative") return "text-negative";
  return "text-zinc-600";
}

/**
 * Backend codes that have a specific human phrasing. Anything not listed here
 * falls back to title-casing the underscores away, so a new backend code is
 * still readable rather than raw.
 */
const LABEL_OVERRIDES: Record<string, string> = {
  ai: "AI",
  api: "API",
  cad: "CAD",
  cagr: "CAGR",
  cvar: "CVaR",
  etf: "ETF",
  fx: "FX",
  ibkr: "IBKR",
  ips: "IPS",
  kyc: "KYC",
  pnl: "P&L",
  qqq: "QQQ",
  roe: "ROE",
  roic: "ROIC",
  spy: "SPY",
  ttm: "TTM",
  usd: "USD",
  var: "VaR",
};

const PHRASE_OVERRIDES: Record<string, string> = {
  approved_for_personal_use: "Approved for personal use",
  attention_required: "Attention required",
  conditional_var_95: "Conditional VaR (95%)",
  insufficient_history: "Insufficient history",
  no_material_change: "No material change",
  not_available: "Not available",
  partial_modeled_current_holdings: "Partial (current holdings model)",
  review_add: "Review — add",
  review_exit: "Review — exit",
  review_hold: "Review — hold",
  review_thesis: "Review — thesis",
  review_trim: "Review — trim",
  sufficient_modeled_current_holdings: "Sufficient (current holdings model)",
  this_week: "This week",
  thesis_incomplete: "Thesis incomplete",
  valuation_not_available: "Valuation not available",
  value_at_risk_95: "Value at risk (95%)",
};

/**
 * Turn a backend code into display copy: `review_trim` → `Review — trim`,
 * `thesis_incomplete` → `Thesis incomplete`, `cvar_95` → `CVaR 95`.
 */
export function humanizeCode(value: unknown, fallback = MISSING): string {
  if (isMissing(value)) return fallback;
  const raw = String(value).trim();
  const key = raw.toLowerCase();
  if (PHRASE_OVERRIDES[key]) return PHRASE_OVERRIDES[key];

  const words = key.split(/[_\-\s]+/).filter(Boolean);
  if (words.length === 0) return fallback;

  return words
    .map((word, index) => {
      const override = LABEL_OVERRIDES[word];
      if (override) return override;
      if (index === 0) return word.charAt(0).toUpperCase() + word.slice(1);
      return word;
    })
    .join(" ");
}

/** Comma-separated list of codes, humanised. */
export function humanizeCodeList(values: unknown, fallback = MISSING): string {
  const list = Array.isArray(values)
    ? values
    : typeof values === "string"
      ? values.split(",")
      : [];
  const humanized = list
    .map((entry) => String(entry).trim())
    .filter((entry) => entry && entry !== "none")
    .map((entry) => humanizeCode(entry));
  return humanized.length > 0 ? humanized.join(", ") : fallback;
}

/** `2026-09-01T01:02:03Z` → `1 Sep 2026, 01:02`. Stable across server/client. */
export function formatDateTime(value: unknown): string {
  if (isMissing(value)) return MISSING;
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

/** `2026-09-01` → `1 Sep 2026`. */
export function formatDate(value: unknown): string {
  if (isMissing(value)) return MISSING;
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export { MISSING };
