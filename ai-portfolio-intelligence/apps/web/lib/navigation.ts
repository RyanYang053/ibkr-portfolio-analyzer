import {
  Activity,
  BookOpen,
  ClipboardList,
  FileBarChart,
  Gauge,
  HeartPulse,
  History,
  LayoutDashboard,
  Layers,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  ShieldQuestion,
  Star,
  Target,
  Telescope,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** One line of orientation, shown in the command palette. */
  hint: string;
  /** Extra terms the command palette should match on. */
  keywords?: string[];
  /**
   * Cheap API paths this destination reads first. Warmed both on hover/focus
   * and during idle time, so the page lands on data that is already cached.
   * `{account}` is replaced with the active account query string.
   */
  prefetch?: string[];
  /**
   * Expensive paths — seconds of server work, not milliseconds. Warmed only on
   * hover or focus, where the pointer has signalled intent. Warming these in
   * the background from every page would re-run the computation constantly for
   * a destination the user may never open.
   */
  prefetchOnIntent?: string[];
};

export type NavGroup = {
  id: string;
  label: string;
  items: NavItem[];
};

/**
 * Single source of truth for in-app destinations: the sidebar, the command
 * palette and the hover prefetcher all read this, so a new page cannot be
 * reachable from one and invisible to the others.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    id: "today",
    label: "Today",
    items: [
      {
        href: "/",
        label: "Dashboard",
        icon: LayoutDashboard,
        hint: "Attention queue, portfolio headline, data health",
        keywords: ["home", "overview", "attention"],
        prefetch: ["/portfolio/summary{account}", "/decisions/queue{account}", "/data-health"],
      },
      {
        href: "/markets",
        label: "Markets",
        icon: TrendingUp,
        hint: "Regime classification and the session calendar",
        keywords: ["regime", "breadth", "calendar", "macro"],
        prefetch: ["/markets/overview", "/markets/calendar"],
      },
      {
        href: "/monitoring",
        label: "Monitoring",
        icon: HeartPulse,
        hint: "Alert inbox and option expiry risk",
        keywords: ["alerts", "inbox", "notifications", "expiry"],
        prefetch: ["/monitoring/events{account}", "/monitoring/notifications{account}"],
      },
    ],
  },
  {
    id: "decide",
    label: "Decide",
    items: [
      {
        href: "/decisions",
        label: "Decisions",
        icon: Scale,
        hint: "The review queue for every held position",
        keywords: ["queue", "review", "packet"],
        prefetch: ["/decisions/queue{account}"],
      },
      {
        href: "/decision-center",
        label: "Decision Center",
        icon: Layers,
        hint: "Deterministic gates and investor lenses",
        keywords: ["gates", "lenses", "thesis"],
        prefetch: ["/portfolio/decision-center{account}"],
      },
      {
        href: "/trade-plans",
        label: "Trade Plans",
        icon: ClipboardList,
        hint: "Sized intentions — never submitted to a broker",
        keywords: ["orders", "sizing", "intent"],
        prefetch: ["/trade-plans{account}"],
      },
      {
        href: "/plan",
        label: "Plan & Policy",
        icon: Target,
        hint: "Goals, account roles and IPS feasibility",
        keywords: ["goals", "ips", "policy", "feasibility"],
        prefetch: ["/planning/plan?plan_id=default"],
      },
    ],
  },
  {
    id: "research",
    label: "Research",
    items: [
      {
        href: "/research",
        label: "Research",
        icon: Telescope,
        hint: "Research queue and the change feed",
        keywords: ["queue", "changes", "notes"],
        prefetch: ["/research/queue{account}", "/research/change-feed{account}"],
      },
      {
        href: "/securities",
        label: "Securities",
        icon: Search,
        hint: "Workspace for any security, held or not",
        keywords: ["ticker", "symbol", "lookup", "chart"],
      },
      {
        href: "/research/screener",
        label: "Screener",
        icon: Search,
        hint: "Surface candidates across holdings and watchlist",
        keywords: ["filter", "screen", "candidates"],
        prefetch: ["/screeners{account}"],
      },
      {
        href: "/watchlist",
        label: "Watchlist",
        icon: Star,
        hint: "Securities monitored without a position",
        keywords: ["monitor", "follow"],
        prefetch: ["/watchlist"],
      },
    ],
  },
  {
    id: "portfolio",
    label: "Portfolio",
    items: [
      {
        href: "/portfolio",
        label: "Holdings",
        icon: ClipboardList,
        hint: "Positions, allocation and risk-adjusted performance",
        keywords: ["positions", "allocation", "holdings", "exposure"],
        prefetch: ["/portfolio/summary{account}", "/portfolio/positions{account}"],
        // Attribution reconstructs a return series per holding and runs for
        // seconds against a real account, so it waits for a hover.
        prefetchOnIntent: ["/portfolio/attribution{account}", "/portfolio/advanced-risk{account}"],
      },
      {
        href: "/portfolio/construction",
        label: "Construction",
        icon: Layers,
        hint: "Scenario comparison against a no-trade baseline",
        keywords: ["rebalance", "optimize", "scenario", "turnover"],
        prefetch: ["/construction/scenarios{account}"],
      },
      {
        href: "/risk",
        label: "Risk Center",
        icon: ShieldCheck,
        hint: "Concentration, drawdown and policy breaches",
        keywords: ["var", "drawdown", "concentration", "volatility", "beta"],
        prefetch: ["/portfolio/risk{account}"],
      },
      {
        href: "/journal",
        label: "Journal",
        icon: BookOpen,
        hint: "Closed-trade review and decision quality",
        keywords: ["trades", "log", "post-mortem"],
        prefetch: ["/journal{account}"],
      },
    ],
  },
  {
    id: "evidence",
    label: "Evidence",
    items: [
      {
        href: "/reports",
        label: "Reports",
        icon: FileBarChart,
        hint: "Monthly reviews and performance history",
        keywords: ["monthly", "performance", "export", "pnl"],
        prefetch: ["/reports", "/portfolio/pnl-history"],
      },
      {
        href: "/history",
        label: "History",
        icon: History,
        hint: "How decisions and outcomes changed over time",
        keywords: ["timeline", "past", "outcomes"],
        prefetch: ["/decisions/queue{account}"],
      },
      {
        href: "/data-health",
        label: "Data Health",
        icon: Activity,
        hint: "What is measured, what is missing, and why",
        keywords: ["coverage", "quality", "missing", "provider"],
        prefetch: ["/data-health"],
      },
      {
        href: "/methodologies",
        label: "Methodologies",
        icon: ShieldQuestion,
        hint: "Approval state of every calculation method",
        keywords: ["governance", "approval", "model"],
        prefetch: ["/methodologies"],
      },
      {
        href: "/audit",
        label: "Audit Log",
        icon: Gauge,
        hint: "Local record of security-relevant activity",
        keywords: ["security", "log", "activity", "events"],
        prefetch: ["/desktop/audit-logs"],
      },
    ],
  },
  {
    id: "setup",
    label: "Setup",
    items: [
      {
        href: "/settings",
        label: "Settings",
        icon: Settings,
        hint: "Broker connection, IPS targets, AI provider, backup",
        keywords: ["config", "preferences", "broker", "flex", "api key", "theme"],
        prefetch: ["/portfolio/profile", "/portfolio/policy"],
      },
      {
        href: "/onboarding",
        label: "Onboarding",
        icon: Target,
        hint: "First-run setup checklist",
        keywords: ["setup", "getting started", "checklist"],
        prefetch: ["/onboarding/state"],
      },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

/**
 * The nav entry a pathname belongs to. Longest matching href wins so
 * `/portfolio/construction` does not resolve to `/portfolio`.
 */
export function activeNavHref(pathname: string): string | null {
  const path = pathname.replace(/\/+$/, "") || "/";
  let best: string | null = null;
  for (const item of NAV_ITEMS) {
    const href = item.href.replace(/\/+$/, "") || "/";
    if (href === "/") {
      if (path === "/") best = item.href;
      continue;
    }
    if ((path === href || path.startsWith(`${href}/`)) && (!best || href.length > best.length)) {
      best = item.href;
    }
  }
  return best;
}
