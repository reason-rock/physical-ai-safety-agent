"use client";

import type { ReactNode } from "react";

/** Card: the standard surface. */
export function Card({
  children,
  className = "",
  hoverable = false,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  hoverable?: boolean;
  as?: React.ElementType;
}) {
  return (
    <Tag className={`card ${hoverable ? "card-hoverable" : ""} ${className}`}>
      {children}
    </Tag>
  );
}

/** Section header: small uppercase label. */
export function SectionTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`section-title ${className}`}>{children}</div>;
}

/** Page header: title + optional subtitle + right-side actions. */
export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-[22px] font-bold leading-tight text-ink text-balance">
          {title}
        </h1>
        {subtitle && (
          <div className="mt-1 text-sm text-muted text-balance">{subtitle}</div>
        )}
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </header>
  );
}

/** Inline badge with semantic colour. */
export function Pill({
  tone = "muted",
  children,
  className = "",
}: {
  tone?: "safe" | "warn" | "danger" | "brand" | "muted";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`pill pill--${tone} ${className}`}>{children}</span>
  );
}

/** Stat block: tiny label + bold value. */
export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <div className="stat-label">{label}</div>
      <div className="stat-value truncate">{value}</div>
      {hint && <div className="mt-0.5 text-[10px] text-faint">{hint}</div>}
    </div>
  );
}

/** Soft, animated progress bar. */
export function Progress({
  value,
  tone = "brand",
}: {
  value: number;
  tone?: "brand" | "safe" | "warn" | "danger";
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const toneClass = {
    brand: "bg-brand-500",
    safe: "bg-safe-500",
    warn: "bg-warn-500",
    danger: "bg-danger-500",
  }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
      <div
        className={`h-full rounded-full ${toneClass} transition-all`}
        style={{ width: `${pct}%`, transitionDuration: "300ms" }}
      />
    </div>
  );
}

/** Empty-state placeholder with optional action. */
export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center justify-center px-8 py-14 text-center">
      <div className="text-sm font-bold uppercase tracking-wider text-faint">
        {title}
      </div>
      {body && <div className="mt-2 max-w-md text-sm text-muted">{body}</div>}
      {action && <div className="mt-5">{action}</div>}
    </Card>
  );
}
