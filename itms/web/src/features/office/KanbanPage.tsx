import { useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useProjectBoard } from "@/shared/api/queries";
import type { BoardCard } from "@/shared/api/types";
import { cn } from "@/shared/lib/cn";
import { PageHeader, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const COLUMNS = ["NEW", "IN_PROGRESS", "BLOCKED", "REVIEW", "DONE", "ON_HOLD"] as const;

const TASK_NEXT: Record<string, string[]> = {
  NEW: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["ON_HOLD", "BLOCKED", "REVIEW", "DONE", "CANCELLED"],
  ON_HOLD: ["IN_PROGRESS", "CANCELLED"],
  BLOCKED: ["IN_PROGRESS", "CANCELLED"],
  REVIEW: ["DONE", "IN_PROGRESS", "CANCELLED"],
  DONE: [],
  CANCELLED: [],
};

export function KanbanPage() {
  const { t, te } = useI18n();
  const queryClient = useQueryClient();
  const { data, isLoading } = useProjectBoard();
  const [busy, setBusy] = useState(false);
  const cards = data ?? [];

  async function move(card: BoardCard, status: string) {
    if (card.status === status) return;
    if (!(TASK_NEXT[card.status] ?? []).includes(status)) {
      toast.error(t("errors.invalid_status_transition"));
      return;
    }
    setBusy(true);
    try {
      await mutations.updateTask(card.project_id, card.id, { status });
      await queryClient.invalidateQueries({ queryKey: keys.projectBoard });
    } catch (err) {
      toast.error(describeError(err, t));
    } finally {
      setBusy(false);
    }
  }

  function onDrop(status: string, event: DragEvent) {
    event.preventDefault();
    const id = event.dataTransfer.getData("text/plain");
    const card = cards.find((item) => item.id === id);
    if (card) void move(card, status);
  }

  return (
    <div className="flex flex-col gap-4" data-testid="office-kanban">
      <PageHeader title={t("nav.kanban")} subtitle={t("office.kanbanHint")} />
      {isLoading ? (
        <div className="flex h-40 items-center justify-center">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          {COLUMNS.map((status) => {
            const column = cards.filter((card) => card.status === status);
            return (
              <section
                key={status}
                className="surface min-h-64 rounded-lg p-2"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => onDrop(status, event)}
              >
                <h2 className="mb-2 flex items-center justify-between text-xs font-medium text-muted">
                  <span>{te("taskStatus", status)}</span>
                  <span className="tabular-nums">{column.length}</span>
                </h2>
                <div className="flex flex-col gap-2">
                  {column.map((card) => (
                    <article
                      key={card.id}
                      draggable={!busy}
                      onDragStart={(event) => event.dataTransfer.setData("text/plain", card.id)}
                      className={cn(
                        "rounded-md border border-app bg-[rgb(var(--surface))] p-2 text-sm",
                        busy && "opacity-60",
                      )}
                    >
                      <p className="font-mono text-[0.65rem] text-muted">{card.label}</p>
                      <p className="mt-0.5">{card.title}</p>
                      <p className="mt-1 truncate text-xs text-muted">{card.project_name}</p>
                      <div className="mt-2 flex items-center justify-between gap-2 text-[11px]">
                        <span className="text-muted">{te("priority", card.priority)}</span>
                        {card.due_date && <span className="tabular-nums">{card.due_date}</span>}
                      </div>
                      <Link
                        to={`/projects/${card.project_id}?task=${card.id}`}
                        className="mt-2 inline-block text-xs text-[rgb(var(--accent))]"
                      >
                        {t("office.openTask")}
                      </Link>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
