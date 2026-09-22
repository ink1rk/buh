import { Plus, Route as RouteIcon, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useConnections,
  useFreePorts,
  useLocations,
  useMeta,
  useRedundancy,
  useRoutes,
  type ConnectionListParams,
} from "@/shared/api/queries";
import type { ConnectionRow, EndpointRef, FreePortsRow } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { EmptyState, FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { Tabs } from "@/shared/ui/Tabs";
import { toast } from "@/shared/ui/toast";

import { ConnectionDialog } from "./ConnectionDialog";
import { TraceDialog } from "./TraceDialog";

const PAGE_SIZE = 50;

type TabId = "connections" | "routes" | "freePorts" | "redundancy";

const CONNECTION_TONE: Record<string, "neutral" | "ok" | "warn" | "danger" | "accent"> = {
  PLANNED: "neutral",
  RESERVED: "accent",
  ACTIVE: "ok",
  FAULTY: "danger",
  DECOMMISSIONED: "neutral",
};

function Endpoint({ end }: { end: EndpointRef | null }) {
  if (!end) return <span className="text-muted">—</span>;
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Link to={`/ci/${end.ci_id}?tab=network`} className="truncate text-accent hover:underline">
        {end.ci_name ?? end.ci_id}
      </Link>
      <span className="shrink-0 font-mono text-xs text-muted">{end.interface_name}</span>
    </span>
  );
}

function RouteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const { data: locations } = useLocations();
  const [form, setForm] = useState<Record<string, string>>({
    name: "",
    route_type: "",
    from_location_id: "",
    to_location_id: "",
    length_m: "",
    capacity: "",
  });
  const [error, setError] = useState<string | null>(null);

  const set = (field: string, value: string) => setForm((state) => ({ ...state, [field]: value }));

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createRoute(body),
    [keys.routes],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setForm({
          name: "",
          route_type: "",
          from_location_id: "",
          to_location_id: "",
          length_m: "",
          capacity: "",
        });
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  const locationOptions = (locations ?? []).map((item) => ({ value: item.id, label: item.path }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("network.addRoute")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!form.name.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                name: form.name.trim(),
                route_type: form.route_type.trim() || null,
                from_location_id: form.from_location_id || null,
                to_location_id: form.to_location_id || null,
                length_m: form.length_m.trim() ? Number(form.length_m) : null,
                capacity: form.capacity.trim() ? Number(form.capacity) : null,
                notes: null,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("ci.name")} required>
          <Input value={form.name} autoFocus onChange={(event) => set("name", event.target.value)} />
        </Field>
        <Field label={t("network.routeType")}>
          <Input value={form.route_type} onChange={(event) => set("route_type", event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ci.location")}>
            <Select
              value={form.from_location_id}
              placeholder="—"
              onChange={(event) => set("from_location_id", event.target.value)}
              options={locationOptions}
            />
          </Field>
          <Field label={t("network.peer")}>
            <Select
              value={form.to_location_id}
              placeholder="—"
              onChange={(event) => set("to_location_id", event.target.value)}
              options={locationOptions}
            />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("network.length")}>
            <Input
              type="number"
              min={0}
              step="0.1"
              value={form.length_m}
              onChange={(event) => set("length_m", event.target.value)}
            />
          </Field>
          <Field label={t("network.capacity")}>
            <Input
              type="number"
              min={0}
              value={form.capacity}
              onChange={(event) => set("capacity", event.target.value)}
            />
          </Field>
        </div>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function ConnectionsTab() {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [traceId, setTraceId] = useState<string | null>(null);
  const debouncedQ = useDebounced(q, 300);

  const params: ConnectionListParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      status: status ? [status] : undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [debouncedQ, status, offset],
  );
  const { data, isFetching } = useConnections(params);

  const columns: Array<Column<ConnectionRow>> = [
    {
      key: "label",
      header: t("network.label"),
      width: "10rem",
      render: (row) => <span className="font-mono text-xs">{row.label ?? "—"}</span>,
    },
    { key: "a_end", header: t("network.port"), render: (row) => <Endpoint end={row.a_end} /> },
    { key: "b_end", header: t("network.peer"), render: (row) => <Endpoint end={row.b_end} /> },
    {
      key: "medium",
      header: t("network.medium"),
      width: "9rem",
      render: (row) => (
        <span className="text-xs text-muted">
          {te("cableMedium", row.medium)}
          {row.category ? ` · ${te("cableCategory", row.category)}` : ""}
        </span>
      ),
    },
    {
      key: "length_m",
      header: t("network.length"),
      width: "7rem",
      align: "right",
      render: (row) => <span className="text-xs tabular-nums">{row.length_m ?? "—"}</span>,
    },
    {
      key: "status",
      header: t("network.status"),
      width: "9rem",
      render: (row) => (
        <span className="flex items-center gap-1.5">
          <Badge tone={CONNECTION_TONE[row.status] ?? "neutral"}>
            {te("connectionStatus", row.status)}
          </Badge>
          {row.is_redundant && <Badge tone="accent">{row.redundancy_group ?? "×2"}</Badge>}
        </span>
      ),
    },
  ];

  return (
    <>
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
            value={status}
            placeholder={`${t("network.status")}: ${t("app.all")}`}
            className="w-48"
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
            options={(meta?.connection_statuses ?? []).map((value) => ({
              value,
              label: te("connectionStatus", value),
            }))}
          />
          {(q || status) && (
            <Button
              variant="ghost"
              size="sm"
              icon={<X size={13} />}
              onClick={() => {
                setQ("");
                setStatus("");
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
          emptyTitle={t("network.emptyConnections")}
          onRowClick={(row) => row.a_end && setTraceId(row.a_end.interface_id)}
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

      <TraceDialog interfaceId={traceId} onClose={() => setTraceId(null)} />
    </>
  );
}

function RoutesTab({ onCreate }: { onCreate: () => void }) {
  const { t } = useI18n();
  const { data: routes } = useRoutes();
  const { data: locations } = useLocations();

  const pathOf = (id: string | null) =>
    locations?.find((item) => item.id === id)?.path ?? "—";

  return (
    <Panel
      bodyClassName={routes?.length ? "p-0" : undefined}
      actions={
        <Button size="sm" icon={<Plus size={13} />} onClick={onCreate}>
          {t("network.addRoute")}
        </Button>
      }
      title={t("network.routes")}
    >
      {!routes?.length ? (
        <EmptyState title={t("app.empty")} />
      ) : (
        <ul className="divide-y divide-[rgb(var(--border))]/60">
          {routes.map((item) => (
            <li key={item.id} className="flex items-center gap-3 px-3 py-1.5 text-sm">
              <RouteIcon size={14} className="shrink-0 text-muted" />
              <span className="w-48 shrink-0 truncate font-medium">{item.name}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-muted">
                {pathOf(item.from_location_id)} → {pathOf(item.to_location_id)}
              </span>
              <span className="shrink-0 text-xs tabular-nums text-muted">
                {item.length_m != null ? `${item.length_m} м` : "—"}
              </span>
              <span className="w-24 shrink-0 text-right text-xs tabular-nums text-muted">
                {item.capacity != null ? `${t("network.capacity")}: ${item.capacity}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function FreePortsTab() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data, isFetching } = useFreePorts();

  const columns: Array<Column<FreePortsRow>> = [
    { key: "name", header: t("ci.name"), render: (row) => <span className="font-medium">{row.name}</span> },
    {
      key: "device_role",
      header: t("devices.role"),
      width: "12rem",
      render: (row) => <span className="text-muted">{te("deviceRole", row.device_role)}</span>,
    },
    {
      key: "total",
      header: t("devices.portsTotal"),
      width: "8rem",
      align: "right",
      render: (row) => <span className="tabular-nums">{row.total}</span>,
    },
    {
      key: "free",
      header: t("devices.portsFree"),
      width: "8rem",
      align: "right",
      render: (row) => (
        <span
          className={`tabular-nums ${row.free === 0 ? "text-[rgb(var(--warn))]" : ""}`}
        >
          {row.free}
        </span>
      ),
    },
  ];

  return (
    <Panel title={t("network.freePorts")} bodyClassName="p-0">
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(row) => row.ci_id}
        loading={isFetching}
        emptyTitle={t("app.empty")}
        onRowClick={(row) => navigate(`/ci/${row.ci_id}?tab=network`)}
      />
    </Panel>
  );
}

function RedundancyTab() {
  const { t, te } = useI18n();
  const { data } = useRedundancy();

  if (!data?.length) {
    return (
      <Panel title={t("network.redundancy")}>
        <EmptyState title={t("network.noIssues")} />
      </Panel>
    );
  }

  return (
    <Panel title={t("network.redundancy")} bodyClassName="p-0">
      <ul className="divide-y divide-[rgb(var(--border))]">
        {data.map((group) => (
          <li key={group.group} className="flex flex-col gap-1.5 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{group.group}</span>
              {group.issues.length ? (
                <Badge tone="warn">{group.issues.length}</Badge>
              ) : (
                <Badge tone="ok">{t("network.noIssues")}</Badge>
              )}
            </div>
            <ul className="flex flex-wrap gap-1.5">
              {group.members.map((member) => (
                <li key={member.id}>
                  <Badge tone={CONNECTION_TONE[member.status] ?? "neutral"}>
                    {member.label ?? member.id.slice(0, 8)} · {te("connectionStatus", member.status)}
                  </Badge>
                </li>
              ))}
            </ul>
            {group.issues.length > 0 && (
              <ul className="flex flex-col gap-0.5">
                {group.issues.map((issue) => (
                  <li key={issue} className="text-xs text-[rgb(var(--warn))]">
                    {issue}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function NetworkPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabId>("connections");
  const [connectOpen, setConnectOpen] = useState(false);
  const [routeOpen, setRouteOpen] = useState(false);

  return (
    <>
      <PageHeader
        title={t("network.title")}
        subtitle={t("network.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={14} />} onClick={() => setConnectOpen(true)}>
            {t("network.connect")}
          </Button>
        }
      />

      <Tabs
        active={tab}
        onChange={(id) => setTab(id as TabId)}
        items={[
          { id: "connections", label: t("network.connections") },
          { id: "routes", label: t("network.routes") },
          { id: "freePorts", label: t("network.freePorts") },
          { id: "redundancy", label: t("network.redundancy") },
        ]}
      />

      {tab === "connections" && <ConnectionsTab />}
      {tab === "routes" && <RoutesTab onCreate={() => setRouteOpen(true)} />}
      {tab === "freePorts" && <FreePortsTab />}
      {tab === "redundancy" && <RedundancyTab />}

      <ConnectionDialog open={connectOpen} onClose={() => setConnectOpen(false)} />
      <RouteDialog open={routeOpen} onClose={() => setRouteOpen(false)} />
    </>
  );
}
