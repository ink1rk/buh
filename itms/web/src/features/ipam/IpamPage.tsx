import { Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  mutations,
  useAddresses,
  useApiMutation,
  useLocations,
  useMeta,
  usePrefix,
  usePrefixes,
  useVlans,
  useVrfs,
} from "@/shared/api/queries";
import type { IpAddressRow, PrefixRow, VlanRow } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { formatPercent } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { EmptyState, FormError, KeyValue, PageHeader, Panel } from "@/shared/ui/Layout";
import { Tabs } from "@/shared/ui/Tabs";
import { toast } from "@/shared/ui/toast";

const PAGE_SIZE = 100;

type TabId = "prefixes" | "vlans" | "addresses";

const IP_STATUS_TONE: Record<string, "neutral" | "ok" | "warn" | "accent"> = {
  ACTIVE: "ok",
  RESERVED: "accent",
  DHCP: "neutral",
  DEPRECATED: "warn",
};

/** Полоса загрузки подсети: 80 % и выше — повод планировать расширение. */
function UtilisationBar({ value }: { value: number }) {
  const tone =
    value >= 90 ? "var(--danger)" : value >= 75 ? "var(--warn)" : "var(--accent)";
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded surface-muted">
        <span
          className="block h-full rounded"
          style={{ width: `${Math.min(value, 100)}%`, background: `rgb(${tone})` }}
        />
      </span>
      <span className="text-xs tabular-nums text-muted">{Math.round(value)} %</span>
    </span>
  );
}

function PrefixDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const { data: vrfs } = useVrfs();
  const { data: vlans } = useVlans({});
  const { data: locations } = useLocations();

  const [form, setForm] = useState<Record<string, string>>({
    cidr: "",
    vrf_id: "",
    vlan_id: "",
    gateway: "",
    site_id: "",
    description: "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (field: string, value: string) => setForm((state) => ({ ...state, [field]: value }));

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createPrefix(body),
    [["ipam", "prefixes"], ["ipam", "vlans"]],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setForm({ cidr: "", vrf_id: "", vlan_id: "", gateway: "", site_id: "", description: "" });
        setError(null);
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("ipam.addPrefix")}
      description={t("ipam.prefixHint")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!form.cidr.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                cidr: form.cidr.trim(),
                vrf_id: form.vrf_id || null,
                vlan_id: form.vlan_id || null,
                gateway: form.gateway.trim() || null,
                site_id: form.site_id || null,
                description: form.description.trim() || null,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("ipam.cidr")} required hint="192.168.10.0/24">
          <Input value={form.cidr} autoFocus onChange={(event) => set("cidr", event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ipam.vrf")}>
            <Select
              value={form.vrf_id}
              placeholder="—"
              onChange={(event) => set("vrf_id", event.target.value)}
              options={(vrfs ?? []).map((item) => ({ value: item.id, label: item.name }))}
            />
          </Field>
          <Field label={t("ipam.vlans")}>
            <Select
              value={form.vlan_id}
              placeholder="—"
              onChange={(event) => set("vlan_id", event.target.value)}
              options={(vlans ?? []).map((item) => ({
                value: item.id,
                label: `${item.vid} — ${item.name}`,
              }))}
            />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ipam.gateway")}>
            <Input value={form.gateway} onChange={(event) => set("gateway", event.target.value)} />
          </Field>
          <Field label={t("ipam.site")}>
            <Select
              value={form.site_id}
              placeholder="—"
              onChange={(event) => set("site_id", event.target.value)}
              options={(locations ?? []).map((item) => ({ value: item.id, label: item.path }))}
            />
          </Field>
        </div>
        <Field label={t("ci.description")}>
          <Input
            value={form.description}
            onChange={(event) => set("description", event.target.value)}
          />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function VlanDialog({
  open,
  vlan,
  onClose,
}: {
  open: boolean;
  vlan: VlanRow | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { data: locations } = useLocations();
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [initialisedFor, setInitialisedFor] = useState<string | null>(null);

  const key = vlan?.id ?? "new";
  if (open && initialisedFor !== key) {
    setInitialisedFor(key);
    setError(null);
    setForm({
      vid: vlan ? String(vlan.vid) : "",
      name: vlan?.name ?? "",
      site_id: vlan?.site_id ?? "",
      purpose: vlan?.purpose ?? "",
      description: vlan?.description ?? "",
    });
  }
  const set = (field: string, value: string) => setForm((state) => ({ ...state, [field]: value }));
  const text = (field: string) => String(form[field] ?? "");

  const save = useApiMutation(
    (body: Record<string, unknown>) =>
      vlan ? mutations.updateVlan(vlan.id, body) : mutations.createVlan(body),
    [["ipam", "vlans"], ["ipam", "prefixes"]],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={vlan ? `VLAN ${vlan.vid}` : t("ipam.addVlan")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!text("vid").trim() || !text("name").trim() || save.isPending}
            onClick={() =>
              save.mutate({
                vid: Number(text("vid")),
                name: text("name").trim(),
                site_id: text("site_id") || null,
                purpose: text("purpose").trim() || null,
                description: text("description").trim() || null,
              })
            }
          >
            {t("app.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-[6rem_1fr]">
          <Field label={t("ipam.vid")} required>
            <Input
              type="number"
              min={1}
              max={4094}
              value={text("vid")}
              onChange={(event) => set("vid", event.target.value)}
            />
          </Field>
          <Field label={t("ci.name")} required>
            <Input value={text("name")} onChange={(event) => set("name", event.target.value)} />
          </Field>
        </div>
        <Field label={t("ipam.site")}>
          <Select
            value={text("site_id")}
            placeholder="—"
            onChange={(event) => set("site_id", event.target.value)}
            options={(locations ?? []).map((item) => ({ value: item.id, label: item.path }))}
          />
        </Field>
        <Field label={t("ipam.purpose")}>
          <Input value={text("purpose")} onChange={(event) => set("purpose", event.target.value)} />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function AddressDialog({
  open,
  initialAddress,
  prefixId,
  onClose,
}: {
  open: boolean;
  initialAddress?: string;
  prefixId?: string;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const [address, setAddress] = useState(initialAddress ?? "");
  const [dnsName, setDnsName] = useState("");
  const [role, setRole] = useState("PRIMARY");
  const [status, setStatus] = useState("ACTIVE");
  const [error, setError] = useState<string | null>(null);
  const [initialisedFor, setInitialisedFor] = useState<string | null>(null);

  // Диалог не размонтируется при закрытии, поэтому форму сбрасываем явно.
  const key = initialAddress ?? "new";
  if (!open && initialisedFor !== null) setInitialisedFor(null);
  if (open && initialisedFor !== key) {
    setInitialisedFor(key);
    setAddress(initialAddress ?? "");
    setError(null);
  }

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createAddress(body),
    [["ipam", "addresses"], ["ipam", "prefixes"]],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setAddress("");
        setDnsName("");
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("ipam.addAddress")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!address.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                address: address.trim(),
                prefix_id: prefixId ?? null,
                dns_name: dnsName.trim() || null,
                role,
                status,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("ipam.address")} required>
          <Input
            value={address}
            autoFocus
            placeholder="192.168.10.25"
            onChange={(event) => setAddress(event.target.value)}
          />
        </Field>
        <Field label={t("ipam.dnsName")}>
          <Input value={dnsName} onChange={(event) => setDnsName(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ipam.role")}>
            <Select
              value={role}
              onChange={(event) => setRole(event.target.value)}
              options={(meta?.ip_roles ?? []).map((value) => ({
                value,
                label: te("ipRole", value),
              }))}
            />
          </Field>
          <Field label={t("network.status")}>
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              options={(meta?.ip_statuses ?? []).map((value) => ({
                value,
                label: te("ipStatus", value),
              }))}
            />
          </Field>
        </div>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function PrefixDetailPanel({ prefixId }: { prefixId: string }) {
  const { t, te, locale } = useI18n();
  const { data } = usePrefix(prefixId);
  const [addressOpen, setAddressOpen] = useState(false);
  const [seed, setSeed] = useState<string | undefined>(undefined);

  const remove = useApiMutation(
    (id: string) => mutations.deleteAddress(id),
    [["ipam", "addresses"], ["ipam", "prefixes"]],
    { onError: (err) => toast.error(describeError(err, t)) },
  );

  if (!data) return null;

  return (
    <>
      <Panel
        title={data.prefix.cidr}
        actions={
          <Button
            size="sm"
            icon={<Plus size={13} />}
            onClick={() => {
              setSeed(undefined);
              setAddressOpen(true);
            }}
          >
            {t("ipam.addAddress")}
          </Button>
        }
      >
        <KeyValue
          items={[
            { label: t("ipam.networkAddress"), value: data.capacity.network_address },
            { label: t("ipam.netmask"), value: data.capacity.netmask },
            { label: t("ipam.broadcast"), value: data.capacity.broadcast_address ?? "—" },
            { label: t("ipam.gateway"), value: data.prefix.gateway ?? "—" },
            { label: t("ipam.vrf"), value: data.prefix.vrf_name ?? "—" },
            { label: t("ipam.vlans"), value: data.prefix.vlan_label ?? "—" },
            { label: t("ipam.usable"), value: data.capacity.usable_total },
            { label: t("ipam.used"), value: data.capacity.used },
            { label: t("ipam.free"), value: data.capacity.free },
            {
              label: t("ipam.utilisation"),
              value: formatPercent(data.capacity.utilisation_pct, locale),
            },
          ]}
        />

        {data.next_free.length > 0 && (
          <div className="mt-3 border-t border-app pt-3">
            <p className="text-xs text-muted">{t("ipam.nextFree")}</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {data.next_free.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setSeed(item);
                    setAddressOpen(true);
                  }}
                  className="rounded border border-app px-1.5 py-0.5 font-mono text-xs text-muted hover:text-app"
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}
      </Panel>

      <Panel title={t("ipam.addresses")} bodyClassName="p-0">
        {!data.addresses.length ? (
          <EmptyState title={t("ipam.emptyAddresses")} />
        ) : (
          <ul className="divide-y divide-[rgb(var(--border))]/60">
            {data.addresses.map((item) => (
              <li key={item.id} className="group flex items-center gap-3 px-3 py-1.5 text-sm">
                <span className="w-36 shrink-0 font-mono text-xs">{item.address}</span>
                <Badge tone={IP_STATUS_TONE[item.status] ?? "neutral"}>
                  {te("ipStatus", item.status)}
                </Badge>
                <span className="min-w-0 flex-1 truncate text-xs text-muted">
                  {item.dns_name ?? "—"}
                </span>
                {item.ci_id ? (
                  <Link
                    to={`/ci/${item.ci_id}?tab=network`}
                    className="shrink-0 truncate text-xs text-accent hover:underline"
                  >
                    {item.ci_name ?? "—"}
                    {item.interface_name ? ` · ${item.interface_name}` : ""}
                  </Link>
                ) : (
                  <span className="shrink-0 text-xs text-muted">—</span>
                )}
                <IconButton
                  label={t("ipam.deleteAddressConfirm")}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={() => remove.mutate(item.id)}
                >
                  <Trash2 size={13} />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <AddressDialog
        open={addressOpen}
        initialAddress={seed}
        prefixId={prefixId}
        onClose={() => setAddressOpen(false)}
      />
    </>
  );
}

function PrefixesTab({ onCreate }: { onCreate: () => void }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [vrfId, setVrfId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const debouncedQ = useDebounced(q, 300);

  const { data: vrfs } = useVrfs();
  const { data, isFetching } = usePrefixes({
    q: debouncedQ || undefined,
    vrf_id: vrfId || undefined,
  });

  const columns: Array<Column<PrefixRow>> = [
    {
      key: "cidr",
      header: t("ipam.cidr"),
      width: "12rem",
      render: (row) => <span className="font-mono text-xs font-medium">{row.cidr}</span>,
    },
    {
      key: "vlan",
      header: t("ipam.vlans"),
      width: "10rem",
      render: (row) => <span className="text-xs text-muted">{row.vlan_label ?? "—"}</span>,
    },
    {
      key: "gateway",
      header: t("ipam.gateway"),
      width: "10rem",
      render: (row) => <span className="font-mono text-xs text-muted">{row.gateway ?? "—"}</span>,
    },
    {
      key: "description",
      header: t("ci.description"),
      render: (row) => <span className="truncate text-xs text-muted">{row.description ?? "—"}</span>,
    },
    {
      key: "used",
      header: t("ipam.used"),
      width: "6rem",
      align: "right",
      render: (row) => <span className="tabular-nums">{row.used}</span>,
    },
    {
      key: "free",
      header: t("ipam.free"),
      width: "6rem",
      align: "right",
      render: (row) => <span className="tabular-nums text-muted">{row.free}</span>,
    },
    {
      key: "utilisation",
      header: t("ipam.utilisation"),
      width: "9rem",
      render: (row) => <UtilisationBar value={row.utilisation_pct} />,
    },
  ];

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-app p-2.5">
          <Input
            value={q}
            placeholder={t("app.search")}
            className="w-56"
            onChange={(event) => setQ(event.target.value)}
          />
          <Select
            value={vrfId}
            placeholder={`${t("ipam.vrf")}: ${t("app.all")}`}
            className="w-44"
            onChange={(event) => setVrfId(event.target.value)}
            options={(vrfs ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
          {(q || vrfId) && (
            <Button
              variant="ghost"
              size="sm"
              icon={<X size={13} />}
              onClick={() => {
                setQ("");
                setVrfId("");
              }}
            >
              {t("app.reset")}
            </Button>
          )}
          <Button
            size="sm"
            variant="primary"
            className="ml-auto"
            icon={<Plus size={13} />}
            onClick={onCreate}
          >
            {t("ipam.addPrefix")}
          </Button>
        </div>

        <DataTable
          columns={columns}
          rows={data ?? []}
          rowKey={(row) => row.id}
          loading={isFetching}
          activeRowKey={selected}
          emptyTitle={t("ipam.emptyPrefixes")}
          onRowClick={(row) => setSelected(row.id)}
        />
      </Panel>

      {selected ? (
        <div className="flex flex-col gap-4">
          <PrefixDetailPanel prefixId={selected} />
        </div>
      ) : (
        <Panel>
          <EmptyState title={t("app.nothingSelected")} hint={t("ipam.prefixHint")} />
        </Panel>
      )}
    </div>
  );
}

function VlansTab() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<{ vlan: VlanRow | null } | null>(null);
  const debouncedQ = useDebounced(q, 300);
  const { data, isFetching } = useVlans({ q: debouncedQ || undefined });

  const columns: Array<Column<VlanRow>> = [
    {
      key: "vid",
      header: t("ipam.vid"),
      width: "6rem",
      render: (row) => <span className="font-mono text-xs font-medium tabular-nums">{row.vid}</span>,
    },
    { key: "name", header: t("ci.name"), render: (row) => row.name },
    {
      key: "site",
      header: t("ipam.site"),
      width: "16rem",
      render: (row) => <span className="truncate text-xs text-muted">{row.site_name ?? "—"}</span>,
    },
    {
      key: "purpose",
      header: t("ipam.purpose"),
      width: "14rem",
      render: (row) => <span className="text-xs text-muted">{row.purpose ?? "—"}</span>,
    },
    {
      key: "prefix_count",
      header: t("ipam.prefixes"),
      width: "8rem",
      align: "right",
      render: (row) => <span className="tabular-nums text-muted">{row.prefix_count}</span>,
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
            onChange={(event) => setQ(event.target.value)}
          />
          <Button
            size="sm"
            variant="primary"
            className="ml-auto"
            icon={<Plus size={13} />}
            onClick={() => setEditing({ vlan: null })}
          >
            {t("ipam.addVlan")}
          </Button>
        </div>

        <DataTable
          columns={columns}
          rows={data ?? []}
          rowKey={(row) => row.id}
          loading={isFetching}
          emptyTitle={t("app.empty")}
          onRowClick={(row) => setEditing({ vlan: row })}
        />
      </Panel>

      {editing && <VlanDialog open vlan={editing.vlan} onClose={() => setEditing(null)} />}
    </>
  );
}

function AddressesTab() {
  const { t, te } = useI18n();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const debouncedQ = useDebounced(q, 300);

  const params = useMemo(
    () => ({ q: debouncedQ || undefined, limit: PAGE_SIZE, offset }),
    [debouncedQ, offset],
  );
  const { data, isFetching } = useAddresses(params);

  const remove = useApiMutation(
    (id: string) => mutations.deleteAddress(id),
    [["ipam", "addresses"], ["ipam", "prefixes"]],
    { onError: (err) => toast.error(describeError(err, t)) },
  );

  const columns: Array<Column<IpAddressRow>> = [
    {
      key: "address",
      header: t("ipam.address"),
      width: "12rem",
      render: (row) => <span className="font-mono text-xs font-medium">{row.address}</span>,
    },
    {
      key: "dns_name",
      header: t("ipam.dnsName"),
      width: "16rem",
      render: (row) => <span className="text-xs text-muted">{row.dns_name ?? "—"}</span>,
    },
    {
      key: "owner",
      header: t("ipam.owner"),
      render: (row) =>
        row.ci_id ? (
          <Link to={`/ci/${row.ci_id}?tab=network`} className="text-accent hover:underline">
            {row.ci_name ?? "—"}
            {row.interface_name && (
              <span className="ml-1.5 font-mono text-xs text-muted">{row.interface_name}</span>
            )}
          </Link>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "role",
      header: t("ipam.role"),
      width: "10rem",
      render: (row) => <span className="text-xs text-muted">{te("ipRole", row.role)}</span>,
    },
    {
      key: "status",
      header: t("network.status"),
      width: "9rem",
      render: (row) => (
        <Badge tone={IP_STATUS_TONE[row.status] ?? "neutral"}>{te("ipStatus", row.status)}</Badge>
      ),
    },
    {
      key: "actions",
      header: "",
      width: "3rem",
      align: "right",
      render: (row) => (
        <IconButton label={t("ipam.deleteAddressConfirm")} onClick={() => remove.mutate(row.id)}>
          <Trash2 size={13} />
        </IconButton>
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
          <span className="text-xs text-muted tabular-nums">
            {t("app.total")}: {data?.total ?? 0}
          </span>
          <Button
            size="sm"
            variant="primary"
            className="ml-auto"
            icon={<Plus size={13} />}
            onClick={() => setAddOpen(true)}
          >
            {t("ipam.addAddress")}
          </Button>
        </div>

        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          loading={isFetching}
          emptyTitle={t("ipam.emptyAddresses")}
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

      <AddressDialog open={addOpen} onClose={() => setAddOpen(false)} />
    </>
  );
}

export function IpamPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabId>("prefixes");
  const [prefixOpen, setPrefixOpen] = useState(false);

  return (
    <>
      <PageHeader title={t("ipam.title")} subtitle={t("ipam.subtitle")} />

      <Tabs
        active={tab}
        onChange={(id) => setTab(id as TabId)}
        items={[
          { id: "prefixes", label: t("ipam.prefixes") },
          { id: "vlans", label: t("ipam.vlans") },
          { id: "addresses", label: t("ipam.addresses") },
        ]}
      />

      {tab === "prefixes" && <PrefixesTab onCreate={() => setPrefixOpen(true)} />}
      {tab === "vlans" && <VlansTab />}
      {tab === "addresses" && <AddressesTab />}

      <PrefixDialog open={prefixOpen} onClose={() => setPrefixOpen(false)} />
    </>
  );
}
