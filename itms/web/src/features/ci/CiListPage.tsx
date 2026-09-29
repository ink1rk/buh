import { Download, Plus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useCiList, useLocations, useMeta, useSession, type CiListParams } from "@/shared/api/queries";
import type { Ci } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { formatRelative } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Checkbox, Input, Select } from "@/shared/ui/Field";
import { PageHeader, Panel } from "@/shared/ui/Layout";

import { CiCreateDialog } from "./CiCreateDialog";

const PAGE_SIZE = 50;

export function CiListPage() {
  const { t, te, locale } = useI18n();
  const { data: session } = useSession();
  const canExport = session?.permissions.includes("export:run") ?? false;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);

  const { data: meta } = useMeta();
  const { data: locations } = useLocations();

  const q = params.get("q") ?? "";
  const ciType = params.get("type") ?? "";
  const status = params.get("status") ?? "";
  const locationId = params.get("location") ?? "";
  const criticality = params.get("criticality") ?? "";
  const missing = params.get("missing") ?? "";
  const archived = params.get("archived") === "1";
  const sort = params.get("sort") ?? "name";
  const offset = Number(params.get("offset") ?? 0);
  const debouncedQ = useDebounced(q, 300);

  const patch = (next: Record<string, string | null>) => {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === null || value === "") updated.delete(key);
      else updated.set(key, value);
    }
    // Любая смена фильтра возвращает на первую страницу — иначе список выглядит пустым.
    if (!("offset" in next)) updated.delete("offset");
    setParams(updated, { replace: true });
  };

  const query: CiListParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      ci_type: ciType ? [ciType] : undefined,
      status: status ? [status] : undefined,
      location_id: locationId || undefined,
      criticality: criticality ? [criticality] : undefined,
      without_owner: missing === "owner" ? true : undefined,
      without_location: missing === "location" ? true : undefined,
      archived,
      sort,
      limit: PAGE_SIZE,
      offset,
    }),
    [debouncedQ, ciType, status, locationId, criticality, missing, archived, sort, offset],
  );

  const { data, isFetching } = useCiList(query);

  const columns: Array<Column<Ci>> = [
    {
      key: "name",
      header: t("ci.name"),
      sortable: true,
      render: (row) => (
        <span className="block min-w-0">
          <span className="flex items-center gap-2">
            {row.code && <span className="font-mono text-xs text-muted">{row.code}</span>}
            {row.archived_at && <Badge>{t("ci.archived")}</Badge>}
          </span>
          <span className="block truncate font-medium">{row.name}</span>
        </span>
      ),
    },
    {
      key: "ci_type",
      header: t("ci.type"),
      width: "11rem",
      render: (row) => <span className="text-muted">{te("ciType", row.ci_type)}</span>,
    },
    {
      key: "status",
      header: t("ci.status"),
      width: "9rem",
      sortable: true,
      render: (row) => (
        <Badge tone={toneFor("ciStatus", row.status)}>{te("ciStatus", row.status)}</Badge>
      ),
    },
    {
      key: "criticality",
      header: t("ci.criticality"),
      width: "8rem",
      render: (row) => (
        <Badge tone={toneFor("criticality", row.criticality)}>
          {te("criticality", row.criticality)}
        </Badge>
      ),
    },
    {
      key: "location",
      header: t("ci.location"),
      width: "16rem",
      render: (row) => (
        <span className="truncate text-muted" title={row.location?.path}>
          {row.location?.name ?? "—"}
        </span>
      ),
    },
    {
      key: "updated_at",
      header: t("ci.updated"),
      width: "9rem",
      align: "right",
      sortable: true,
      render: (row) => <span className="text-xs text-muted">{formatRelative(row.updated_at, locale)}</span>,
    },
  ];

  const hasFilters = Boolean(q || ciType || status || locationId || criticality || missing || archived);

  return (
    <>
      <PageHeader
        title={t("ci.title")}
        subtitle={t("ci.subtitle")}
        actions={
          <>
            {canExport && (
              <Button
                data-testid="ci-export"
                icon={<Download size={14} />}
                onClick={() => {
                  const search = new URLSearchParams();
                  if (debouncedQ) search.set("q", debouncedQ);
                  if (ciType) search.set("ci_type", ciType);
                  if (status) search.set("status", status);
                  if (criticality) search.set("criticality", criticality);
                  if (locationId) search.set("location_id", locationId);
                  if (archived) search.set("archived", "true");
                  window.location.assign(`/api/v1/exports/ci.csv?${search.toString()}`);
                }}
              >
                {t("ci.exportCsv")}
              </Button>
            )}
            <Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
              {t("ci.create")}
            </Button>
          </>
        }
      />

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-app p-2.5">
          <Input
            value={q}
            placeholder={t("app.search")}
            onChange={(event) => patch({ q: event.target.value })}
            className="w-64"
          />
          <Select
            value={ciType}
            placeholder={`${t("ci.type")}: ${t("app.all")}`}
            onChange={(event) => patch({ type: event.target.value })}
            className="w-44"
            options={(meta?.ci_types ?? []).map((value) => ({
              value,
              label: te("ciType", value),
            }))}
          />
          <Select
            value={status}
            placeholder={`${t("ci.status")}: ${t("app.all")}`}
            onChange={(event) => patch({ status: event.target.value })}
            className="w-44"
            options={(meta?.ci_statuses ?? []).map((value) => ({
              value,
              label: te("ciStatus", value),
            }))}
          />
          <Select
            value={criticality}
            placeholder={`${t("ci.criticality")}: ${t("app.all")}`}
            onChange={(event) => patch({ criticality: event.target.value })}
            className="w-44"
            options={(meta?.criticalities ?? []).map((value) => ({
              value,
              label: te("criticality", value),
            }))}
          />
          <Select
            value={locationId}
            placeholder={`${t("ci.location")}: ${t("app.all")}`}
            onChange={(event) => patch({ location: event.target.value })}
            className="w-64"
            options={(locations ?? []).map((location) => ({
              value: location.id,
              label: location.path,
            }))}
          />
          <Checkbox
            label={t("ci.archived")}
            checked={archived}
            onChange={(event) => patch({ archived: event.target.checked ? "1" : null })}
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
          <span className="ml-auto text-xs text-muted tabular-nums">
            {t("app.total")}: {data?.total ?? 0}
          </span>
        </div>

        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          loading={isFetching}
          sort={sort}
          onSortChange={(value) => patch({ sort: value })}
          emptyTitle={t("app.empty")}
          emptyHint={hasFilters ? t("ci.emptyFiltered") : t("ci.emptyHint")}
          onRowClick={(row) => navigate(`/ci/${row.id}`)}
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

      <CiCreateDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}
