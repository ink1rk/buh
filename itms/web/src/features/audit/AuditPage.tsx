import { X } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useAudit, useMeta, type AuditParams } from "@/shared/api/queries";
import type { AuditLog } from "@/shared/api/types";
import { formatAuditValue, formatDateTime } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Input, Select } from "@/shared/ui/Field";
import { PageHeader, Panel } from "@/shared/ui/Layout";

const PAGE_SIZE = 50;

const ENTITY_TYPES = [
  "CI",
  "LOCATION",
  "DOCUMENT",
  "EMPLOYEE",
  "USER",
  "CI_RELATION",
  "ORGANIZATION",
];

export function AuditPage() {
  const { t, te, locale } = useI18n();
  const [params, setParams] = useSearchParams();
  const { data: meta } = useMeta();

  const entityType = params.get("entity_type") ?? "";
  const action = params.get("action") ?? "";
  const field = params.get("field") ?? "";
  const dateFrom = params.get("date_from") ?? "";
  const offset = Number(params.get("offset") ?? 0);

  const patch = (next: Record<string, string | null>) => {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (!value) updated.delete(key);
      else updated.set(key, value);
    }
    if (!("offset" in next)) updated.delete("offset");
    setParams(updated, { replace: true });
  };

  const query: AuditParams = useMemo(
    () => ({
      entity_type: entityType || undefined,
      action: action ? [action] : undefined,
      field: field || undefined,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [entityType, action, field, dateFrom, offset],
  );

  const { data, isFetching } = useAudit(query);

  const columns: Array<Column<AuditLog>> = [
    {
      key: "occurred_at",
      header: t("audit.when"),
      width: "11rem",
      render: (row) => (
        <span className="text-xs whitespace-nowrap text-muted">
          {formatDateTime(row.occurred_at, locale)}
        </span>
      ),
    },
    {
      key: "actor",
      header: t("audit.who"),
      width: "12rem",
      render: (row) => <span className="text-xs">{row.actor_label ?? row.actor_kind}</span>,
    },
    {
      key: "action",
      header: t("audit.action"),
      width: "9rem",
      render: (row) => (
        <Badge tone={toneFor("auditAction", row.action)}>{te("auditAction", row.action)}</Badge>
      ),
    },
    {
      key: "entity",
      header: t("audit.entity"),
      width: "18rem",
      render: (row) => (
        <span className="flex min-w-0 flex-col">
          {row.entity_type === "CI" && row.entity_id ? (
            <Link to={`/ci/${row.entity_id}`} className="truncate text-accent hover:underline">
              {row.entity_label ?? row.entity_id}
            </Link>
          ) : (
            <span className="truncate">{row.entity_label ?? "—"}</span>
          )}
          <span className="text-[0.7rem] text-muted">{te("entityType", row.entity_type)}</span>
        </span>
      ),
    },
    {
      key: "changes",
      header: t("audit.field"),
      render: (row) =>
        row.changes.length ? (
          <ul className="flex flex-col gap-0.5">
            {row.changes.slice(0, 4).map((change, index) => (
              <li key={index} className="text-xs">
                <span className="text-muted">{change.field}: </span>
                <span className="text-muted line-through">
                  {formatAuditValue(change.old_value)}
                </span>
                <span className="mx-1 text-muted">→</span>
                <span>{formatAuditValue(change.new_value)}</span>
              </li>
            ))}
            {row.changes.length > 4 && (
              <li className="text-xs text-muted">
                {t("app.more")}: {row.changes.length - 4}
              </li>
            )}
          </ul>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "origin",
      header: t("audit.origin"),
      width: "16rem",
      render: (row) => {
        const refs = [
          row.project_id && `${t("ci.inProject")} ${row.project_id.slice(0, 8)}`,
          row.change_id && `${t("ci.inChange")} ${row.change_id.slice(0, 8)}`,
          row.task_id && `${t("ci.inTask")} ${row.task_id.slice(0, 8)}`,
          row.document_id && `${t("ci.inDocument")} ${row.document_id.slice(0, 8)}`,
        ].filter(Boolean) as string[];
        if (!row.reason && !refs.length) {
          return <span className="text-xs text-muted">{t("audit.noOrigin")}</span>;
        }
        return (
          <span className="flex flex-col gap-0.5">
            {row.reason && <span className="text-xs">{row.reason}</span>}
            {refs.length > 0 && (
              <span className="font-mono text-[0.7rem] text-muted">{refs.join(" · ")}</span>
            )}
          </span>
        );
      },
    },
  ];

  const hasFilters = Boolean(entityType || action || field || dateFrom);

  return (
    <>
      <PageHeader title={t("audit.title")} subtitle={t("audit.subtitle")} />

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-app p-2.5">
          <Select
            value={entityType}
            placeholder={`${t("audit.entity")}: ${t("app.all")}`}
            onChange={(event) => patch({ entity_type: event.target.value })}
            className="w-48"
            options={ENTITY_TYPES.map((value) => ({ value, label: te("entityType", value) }))}
          />
          <Select
            value={action}
            placeholder={`${t("audit.action")}: ${t("app.all")}`}
            onChange={(event) => patch({ action: event.target.value })}
            className="w-44"
            options={(meta?.audit_actions ?? []).map((value) => ({
              value,
              label: te("auditAction", value),
            }))}
          />
          <Input
            value={field}
            placeholder={t("audit.field")}
            onChange={(event) => patch({ field: event.target.value })}
            className="w-44"
          />
          <Input
            type="date"
            value={dateFrom}
            onChange={(event) => patch({ date_from: event.target.value })}
            className="w-40"
          />
          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              icon={<X size={13} />}
              onClick={() => setParams(new URLSearchParams(), { replace: true })}
            >
              {t("app.reset")}
            </Button>
          )}
          <span className="ml-auto text-xs tabular-nums text-muted">
            {t("app.total")}: {data?.total ?? 0}
          </span>
        </div>

        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          loading={isFetching}
          emptyTitle={t("app.empty")}
        />

        <Pagination
          total={data?.total ?? 0}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={(value) => patch({ offset: String(value) })}
          labels={{
            previous: t("app.previous"),
            next: t("app.next"),
            range: (from, to, total) => t("app.range", { from, to, total }),
          }}
        />
      </Panel>
    </>
  );
}
