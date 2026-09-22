import type { ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("surface shadow-card rounded-xl", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-app px-4 py-3">
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {actions && <div className="flex items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[1.65rem] leading-none font-semibold tracking-[-0.03em]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Metric({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: "default" | "warn" | "danger";
  hint?: string;
}) {
  const color =
    tone === "danger"
      ? "text-[rgb(var(--danger))]"
      : tone === "warn"
        ? "text-[rgb(var(--warn))]"
        : "text-app";
  return (
    <div className="surface shadow-card rounded-xl px-4 py-3.5" title={hint}>
      <p className="text-[0.7rem] font-medium tracking-[0.12em] text-muted uppercase">{label}</p>
      <p className={cn("mt-2 text-[1.65rem] leading-none font-semibold tabular-nums tracking-tight", color)}>
        {value}
      </p>
    </div>
  );
}

/**
 * Ошибка сохранения рядом с формой. Всплывающее уведомление исчезает и легко
 * теряется, а причина отказа нужна ровно там, где её исправляют.
 */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="rounded-lg border border-[rgb(var(--danger)/0.35)] bg-[rgb(var(--danger)/0.1)] px-3 py-2 text-sm text-[rgb(var(--danger))]"
    >
      {message}
    </p>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-4 py-14 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-sm text-sm text-muted">{hint}</p>}
      {action}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-app",
        "border-t-[rgb(var(--accent))]",
        className,
      )}
    />
  );
}

export function KeyValue({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-1.5 text-sm">
      {items.map((item, index) => (
        <div key={index} className="contents">
          <dt className="text-xs text-muted leading-5">{item.label}</dt>
          <dd className="min-w-0 break-words leading-5">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Горизонтальная полоса-распределение: наглядно и без графической библиотеки. */
export function BarList({
  items,
  emptyLabel,
}: {
  items: Array<{ label: string; count: number; tone?: string }>;
  emptyLabel: string;
}) {
  const max = items.reduce((acc, item) => Math.max(acc, item.count), 0);
  if (!items.length) return <p className="text-xs text-muted">{emptyLabel}</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((item) => (
        <li key={item.label} className="grid grid-cols-[1fr_3rem] items-center gap-2">
          <div className="min-w-0">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-xs">{item.label}</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full surface-muted">
              <div
                className="h-full rounded-full bg-[rgb(var(--accent))]"
                style={{ width: `${max ? (item.count / max) * 100 : 0}%` }}
              />
            </div>
          </div>
          <span className="text-right text-xs tabular-nums text-muted">{item.count}</span>
        </li>
      ))}
    </ul>
  );
}
