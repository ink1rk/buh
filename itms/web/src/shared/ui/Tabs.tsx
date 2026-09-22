import type { ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

export interface TabItem {
  id: string;
  label: ReactNode;
  badge?: number;
}

export function Tabs({
  items,
  active,
  onChange,
  className,
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex gap-0.5 border-b border-app", className)} role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          onClick={() => onChange(item.id)}
          className={cn(
            "-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-xs font-medium transition-colors",
            active === item.id
              ? "border-[rgb(var(--accent))] text-app"
              : "border-transparent text-muted hover:text-app",
          )}
        >
          {item.label}
          {item.badge !== undefined && item.badge > 0 && (
            <span className="rounded surface-muted px-1 text-[0.65rem] tabular-nums">
              {item.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
