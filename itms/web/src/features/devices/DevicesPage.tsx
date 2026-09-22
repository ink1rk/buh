import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useDevices, useLocations, useMeta, useWarranty, type DeviceListParams } from "@/shared/api/queries";
import type { DeviceRow } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { formatDate } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Input, Select } from "@/shared/ui/Field";
import { EmptyState, PageHeader, Panel } from "@/shared/ui/Layout";

const PAGE_SIZE = 50;
const WARRANTY_HORIZON = 90;

export function DevicesPage() {
  const { t, te, locale } = useI18n();
  const navigate = useNavigate();
  const { data: meta } = useMeta();
  const { data: locations } = useLocations();

  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [locationId, setLocationId] = useState("");
  const [offset, setOffset] = useState(0);
  const debouncedQ = useDebounced(q, 300);

  const params: DeviceListParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      role: role ? [role] : undefined,
      location_id: locationId || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [debouncedQ, role, locationId, offset],
  );

  const { data, isFetching } = useDevices(params);
  const { data: warranty } = useWarranty(WARRANTY_HORIZON);

  const columns: Array<Column<DeviceRow>> = [
    {
      key: "code",
      header: t("ci.code"),
      width: "8rem",
      render: (row) => <span className="font-mono text-xs text-muted">{row.code ?? "—"}</span>,
    },
    {
      key: "name",
      header: t("ci.name"),
      render: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "device_role",
      header: t("devices.role"),
      width: "11rem",
      render: (row) => <span className="text-muted">{te("deviceRole", row.device_role)}</span>,
    },
    {
      key: "model_label",
      header: t("devices.model"),
      width: "14rem",
      render: (row) => <span className="truncate text-muted">{row.model_label ?? "—"}</span>,
    },
    {
      key: "hostname",
      header: t("devices.hostname"),
      width: "12rem",
      render: (row) => <span className="font-mono text-xs">{row.hostname ?? "—"}</span>,
    },
    {
      key: "mgmt_ip",
      header: t("devices.mgmtIp"),
      width: "10rem",
      render: (row) => <span className="font-mono text-xs">{row.mgmt_ip ?? "—"}</span>,
    },
    {
      key: "status",
      header: t("ci.status"),
      width: "8rem",
      render: (row) => (
        <Badge tone={toneFor("ciStatus", row.status)}>{te("ciStatus", row.status)}</Badge>
      ),
    },
    {
      key: "warranty_until",
      header: t("devices.warrantyUntil"),
      width: "9rem",
      align: "right",
      render: (row) => (
        <span className="text-xs text-muted">{formatDate(row.warranty_until, locale)}</span>
      ),
    },
  ];

  const hasFilters = Boolean(q || role || locationId);

  return (
    <>
      <PageHeader title={t("devices.title")} subtitle={t("devices.subtitle")} />

      <div className="grid gap-4 xl:grid-cols-[1fr_18rem]">
        <Panel bodyClassName="p-0">
          <div className="flex flex-wrap items-center gap-2 border-b border-app p-2.5">
            <Input
              value={q}
              placeholder={t("app.search")}
              className="w-56"
              onChange={(event) => {
                setQ(event.target.value);
                setOffset(0);
              }}
            />
            <Select
              value={role}
              placeholder={`${t("devices.role")}: ${t("app.all")}`}
              className="w-48"
              onChange={(event) => {
                setRole(event.target.value);
                setOffset(0);
              }}
              options={(meta?.device_roles ?? []).map((value) => ({
                value,
                label: te("deviceRole", value),
              }))}
            />
            <Select
              value={locationId}
              placeholder={`${t("ci.location")}: ${t("app.all")}`}
              className="w-64"
              onChange={(event) => {
                setLocationId(event.target.value);
                setOffset(0);
              }}
              options={(locations ?? []).map((item) => ({ value: item.id, label: item.path }))}
            />
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                icon={<X size={13} />}
                onClick={() => {
                  setQ("");
                  setRole("");
                  setLocationId("");
                  setOffset(0);
                }}
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
            emptyTitle={t("app.empty")}
            emptyHint={t("devices.empty")}
            onRowClick={(row) => navigate(`/ci/${row.id}?tab=network`)}
          />

          <Pagination
            total={data?.total ?? 0}
            limit={PAGE_SIZE}
            offset={offset}
            onChange={setOffset}
            labels={{
              previous: t("app.previous"),
              next: t("app.next"),
              range: (from, to, total) => t("app.range", { from, to, total }),
            }}
          />
        </Panel>

        <Panel
          title={t("devices.warrantyExpiring")}
          bodyClassName={warranty?.length ? "p-0" : undefined}
        >
          {!warranty?.length ? (
            <EmptyState title={t("network.noIssues")} />
          ) : (
            <ul className="divide-y divide-[rgb(var(--border))]/60">
              {warranty.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/ci/${item.id}?tab=network`)}
                    className="row-hover flex w-full items-center gap-2 px-3 py-1.5 text-left"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm">{item.name}</span>
                    <span className="shrink-0 text-xs tabular-nums text-[rgb(var(--warn))]">
                      {formatDate(item.warranty_until, locale)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
