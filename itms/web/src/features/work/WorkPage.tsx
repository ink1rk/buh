import { useNavigate } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { useInbox } from "@/shared/api/queries";
import type { InboxItem } from "@/shared/api/types";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { EmptyState, PageHeader, Panel, Spinner } from "@/shared/ui/Layout";

const BUCKETS: Array<{ id: string; labelKey: TranslationKey }> = [
  { id: "overdue", labelKey: "projects.overdue" },
  { id: "today", labelKey: "projects.today" },
  { id: "upcoming", labelKey: "projects.upcoming" },
  { id: "undated", labelKey: "projects.undated" },
  { id: "later", labelKey: "projects.later" },
];

export function WorkPage() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data, isPending } = useInbox();
  const items = data ?? [];

  const open = (item: InboxItem) => {
    navigate(`/projects/${item.project_id}?task=${item.id}`);
  };

  return (
    <>
      <PageHeader title={t("nav.work")} subtitle={t("dashboard.myWork")} />
      {isPending ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <Panel>
          <EmptyState title={t("dashboard.noTasks")} hint={t("dashboard.noTasksHint")} />
        </Panel>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {BUCKETS.map((bucket) => {
            const rows = items.filter((item) => item.bucket === bucket.id);
            if (!rows.length) return null;
            return (
              <Panel key={bucket.id} title={`${t(bucket.labelKey)} · ${rows.length}`} bodyClassName="p-0">
                <ul>
                  {rows.map((item) => (
                    <li key={item.id} className="border-b border-app last:border-0">
                      <button
                        type="button"
                        onClick={() => open(item)}
                        className="flex w-full items-start justify-between gap-3 px-4 py-2.5 text-left hover:bg-[rgb(var(--surface-muted))]"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{item.title}</span>
                          <span className="mt-0.5 block text-xs text-muted">
                            <span className="font-mono">{item.label}</span>
                            {" · "}
                            {item.project_name}
                            {item.due_date ? ` · ${item.due_date}` : ""}
                          </span>
                        </span>
                        <Badge tone={toneFor("criticality", item.priority)}>{te("priority", item.priority)}</Badge>
                      </button>
                    </li>
                  ))}
                </ul>
              </Panel>
            );
          })}
        </div>
      )}
    </>
  );
}
