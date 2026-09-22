import type { ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

import { EmptyState, Spinner } from "./Layout";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right";
  sortable?: boolean;
  className?: string;
}

interface DataTableProps<T> {
  columns: Array<Column<T>>;
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  emptyTitle: string;
  emptyHint?: string;
  onRowClick?: (row: T) => void;
  activeRowKey?: string | null;
  sort?: string;
  onSortChange?: (sort: string) => void;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  emptyTitle,
  emptyHint,
  onRowClick,
  activeRowKey,
  sort,
  onSortChange,
}: DataTableProps<T>) {
  if (loading && !rows.length) {
    return (
      <div className="flex items-center justify-center py-10">
        <Spinner />
      </div>
    );
  }
  if (!rows.length) return <EmptyState title={emptyTitle} hint={emptyHint} />;

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    onSortChange(sort === key ? `-${key}` : sort === `-${key}` ? key : key);
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-app text-left">
            {columns.map((column) => {
              const active = sort === column.key || sort === `-${column.key}`;
              return (
                <th
                  key={column.key}
                  style={column.width ? { width: column.width } : undefined}
                  className={cn(
                    "px-3 py-2.5 text-[0.68rem] font-semibold tracking-[0.08em] text-muted uppercase",
                    column.align === "right" && "text-right",
                    column.sortable && onSortChange && "cursor-pointer select-none hover:text-app",
                  )}
                  onClick={column.sortable ? () => toggleSort(column.key) : undefined}
                >
                  <span className="inline-flex items-center gap-1">
                    {column.header}
                    {active && <span aria-hidden>{sort?.startsWith("-") ? "↓" : "↑"}</span>}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn(
                  "border-b border-app/60 row-hover",
                  onRowClick && "cursor-pointer",
                  activeRowKey === key && "bg-[rgb(var(--accent-soft))]",
                )}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "px-3 py-2.5 align-middle",
                      column.align === "right" && "text-right tabular-nums",
                      column.className,
                    )}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
  labels,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
  labels: { previous: string; next: string; range: (from: number, to: number, total: number) => string };
}) {
  if (total <= limit) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <div className="flex items-center justify-between gap-3 border-t border-app px-3 py-2 text-xs text-muted">
      <span className="tabular-nums">{labels.range(from, to, total)}</span>
      <div className="flex gap-1.5">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
          className="rounded-lg border border-app px-2.5 py-1 disabled:opacity-40 hover:not-disabled:text-app"
        >
          {labels.previous}
        </button>
        <button
          type="button"
          disabled={to >= total}
          onClick={() => onChange(offset + limit)}
          className="rounded-lg border border-app px-2.5 py-1 disabled:opacity-40 hover:not-disabled:text-app"
        >
          {labels.next}
        </button>
      </div>
    </div>
  );
}
