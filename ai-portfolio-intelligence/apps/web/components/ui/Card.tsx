import type { ReactNode } from "react";

type CardProps = {
  children: ReactNode;
  className?: string;
  /** Draws attention to a policy breach or a degraded subsystem. */
  tone?: "default" | "accent" | "positive" | "warning" | "negative";
  padding?: "none" | "sm" | "md";
};

const toneRing: Record<NonNullable<CardProps["tone"]>, string> = {
  default: "border-hairline",
  accent: "border-accent-border",
  positive: "border-positive-border",
  warning: "border-warning-border",
  negative: "border-negative-border",
};

const paddings: Record<NonNullable<CardProps["padding"]>, string> = {
  none: "",
  sm: "p-3",
  md: "p-4",
};

/** The single raised surface used across the app. */
export function Card({ children, className = "", tone = "default", padding = "md" }: CardProps) {
  return (
    <div
      className={`rounded-lg border bg-surface shadow-sm ${toneRing[tone]} ${paddings[padding]} ${className}`}
    >
      {children}
    </div>
  );
}

type CardHeaderProps = {
  title: ReactNode;
  /** Short explanation of what the panel measures. */
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
};

export function CardHeader({ title, description, icon, actions, className = "" }: CardHeaderProps) {
  return (
    <div className={`mb-3 flex items-start justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 text-[15px] font-semibold leading-6 text-zinc-900">
          {icon}
          <span className="truncate">{title}</span>
        </h3>
        {description ? <p className="mt-0.5 text-xs leading-5 text-zinc-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** A labelled section inside a card, without a second border. */
export function CardSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-hairline pt-3 first:border-t-0 first:pt-0">
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">{title}</h4>
      {children}
    </section>
  );
}
