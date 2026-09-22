import { useI18n } from "@/i18n";
import { useAnalytics } from "@/shared/api/queries";
import { PageHeader, Panel } from "@/shared/ui/Layout";

function Bars({
  rows,
  label,
}: {
  rows: Array<{ key: string; label: string; value: number }>;
  label: (value: string) => string;
}) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="flex flex-col gap-2">
      {rows.map((row) => (
        <div key={row.key}>
          <div className="mb-1 flex justify-between text-xs">
            <span>{label(row.key)}</span>
            <span className="tabular-nums text-muted">{row.value}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded bg-[rgb(var(--surface-muted))]">
            <div
              className="h-full bg-[rgb(var(--accent))]"
              style={{ width: `${Math.round((100 * row.value) / max)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function AnalyticsPage() {
  const { t, te } = useI18n();
  const { data, isLoading } = useAnalytics();
  if (isLoading || !data) return <p className="text-sm text-muted">{t("app.loading")}</p>;
  const statusRows = Object.entries(data.by_status).map(([key, value]) => ({ key, label: key, value }));
  const priorityRows = Object.entries(data.by_priority).map(([key, value]) => ({
    key,
    label: key,
    value,
  }));
  return (
    <div data-testid="analytics-page">
      <PageHeader title={t("nav.analytics")} />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        {[
          [t("projects.openTasks"), data.open],
          [t("projects.overdue"), data.overdue],
          [t("projects.completed"), data.completed],
        ].map(([label, value]) => (
          <section key={String(label)} className="surface rounded-lg p-3">
            <p className="text-xs text-muted">{label}</p>
            <p className="text-2xl font-medium tabular-nums">{value}</p>
          </section>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={t("projects.status")}>
          <Bars rows={statusRows} label={(value) => te("taskStatus", value)} />
        </Panel>
        <Panel title={t("projects.priority")}>
          <Bars rows={priorityRows} label={(value) => te("priority", value)} />
        </Panel>
        <Panel title={t("nav.directory")}>
          {data.workload.length === 0 ? (
            <p className="text-sm text-muted">{t("app.empty")}</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {data.workload.map((row) => (
                <li key={row.name} className="flex justify-between gap-3">
                  <span>{row.name}</span>
                  <span className="tabular-nums text-muted">
                    {row.open} · {Math.round(row.estimate_min / 60)}ч
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
