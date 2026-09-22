import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useDashboard } from "@/shared/api/queries";
import { formatPercent, formatRelative } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { BarList, EmptyState, Metric, PageHeader, Panel, Spinner } from "@/shared/ui/Layout";

export function DashboardPage() {
  const { t, te, locale } = useI18n();
  const { data, isPending } = useDashboard();

  if (isPending || !data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const { counters, data_quality: quality } = data;
  const coverage = quality.provenance.coverage_pct;

  return (
    <>
      <PageHeader title={t("dashboard.title")} subtitle={t("dashboard.subtitle")} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Metric label={t("dashboard.ciTotal")} value={counters.ci_total} />
        <Metric
          label={t("dashboard.ciCritical")}
          value={counters.ci_critical}
          tone={counters.ci_critical ? "warn" : "default"}
        />
        <Metric
          label={t("dashboard.ciAttention")}
          value={counters.ci_attention}
          tone={counters.ci_attention ? "danger" : "default"}
        />
        <Metric label={t("dashboard.locations")} value={counters.locations} />
        <Metric label={t("dashboard.employees")} value={counters.employees_active} />
        <Metric label={t("dashboard.documents")} value={counters.documents} />
        <Metric
          label={t("dashboard.documentsReview")}
          value={counters.documents_review_due}
          tone={counters.documents_review_due ? "warn" : "default"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title={t("dashboard.byType")}>
          <BarList
            emptyLabel={t("app.empty")}
            items={data.ci_by_type.map((row) => ({
              label: te("ciType", row.key),
              count: row.count,
            }))}
          />
        </Panel>
        <Panel title={t("dashboard.byStatus")}>
          <BarList
            emptyLabel={t("app.empty")}
            items={data.ci_by_status.map((row) => ({
              label: te("ciStatus", row.key),
              count: row.count,
            }))}
          />
        </Panel>
        <Panel title={t("dashboard.byCriticality")}>
          <BarList
            emptyLabel={t("app.empty")}
            items={data.ci_by_criticality.map((row) => ({
              label: te("criticality", row.key),
              count: row.count,
            }))}
          />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <Panel title={t("dashboard.activity")} bodyClassName="p-0">
          {data.recent_activity.length === 0 ? (
            <EmptyState title={t("app.empty")} />
          ) : (
            <ul className="divide-y divide-[rgb(var(--border))]">
              {data.recent_activity.map((item) => (
                <li key={item.id} className="flex items-start gap-3 px-3 py-2 text-sm">
                  <Badge tone={toneFor("auditAction", item.action)}>
                    {te("auditAction", item.action)}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="truncate">
                      {item.entity_type === "CI" && item.entity_id ? (
                        <Link to={`/ci/${item.entity_id}`} className="text-accent hover:underline">
                          {item.entity_label ?? item.entity_id}
                        </Link>
                      ) : (
                        (item.entity_label ?? te("entityType", item.entity_type))
                      )}
                      <span className="text-muted"> · {te("entityType", item.entity_type)}</span>
                    </p>
                    {item.reason && <p className="truncate text-xs text-muted">{item.reason}</p>}
                  </div>
                  <div className="shrink-0 text-right text-xs text-muted">
                    <p>{item.actor_label ?? "—"}</p>
                    <p>{formatRelative(item.occurred_at, locale)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title={t("dashboard.dataQuality")}>
          <div className="flex flex-col gap-3">
            <div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-muted">{t("dashboard.provenanceCoverage")}</span>
                <span className="text-sm font-semibold tabular-nums">
                  {formatPercent(coverage, locale)}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded surface-muted">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${Math.min(coverage, 100)}%`,
                    background:
                      coverage >= 80
                        ? "rgb(var(--ok))"
                        : coverage >= 50
                          ? "rgb(var(--warn))"
                          : "rgb(var(--danger))",
                  }}
                />
              </div>
              <p className="mt-1.5 text-xs text-muted">{t("dashboard.provenanceHint")}</p>
            </div>

            <dl className="flex flex-col gap-1.5 border-t border-app pt-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <dt className="text-xs text-muted">{t("dashboard.withoutLocation")}</dt>
                <dd className="tabular-nums">{quality.ci_without_location}</dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-xs text-muted">{t("dashboard.withoutOwner")}</dt>
                <dd className="tabular-nums">{quality.ci_without_owner}</dd>
              </div>
            </dl>
          </div>
        </Panel>
      </div>
    </>
  );
}
