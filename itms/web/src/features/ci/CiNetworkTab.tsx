import { Cable, Pencil, Plus, Route, Trash2, Unplug, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { ApiError, type Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useDevice,
  useDeviceInterfaces,
  useDeviceModels,
  useMeta,
  usePortUsage,
} from "@/shared/api/queries";
import type { Device, InterfaceRow } from "@/shared/api/types";
import { formatDate } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { EmptyState, FormError, KeyValue, Metric, Panel, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ConnectionDialog } from "../network/ConnectionDialog";
import { InterfaceDialog } from "../network/InterfaceDialog";
import { TraceDialog } from "../network/TraceDialog";
import { ConfirmDialog, ReasonField } from "../provenance/ReasonField";

function ProfileForm({
  ciId,
  device,
  onDone,
}: {
  ciId: string;
  device: Device | null;
  onDone: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: models } = useDeviceModels({ limit: 200, offset: 0 });

  const [form, setForm] = useState<Record<string, string>>({
    device_model_id: device?.device_model_id ?? "",
    device_role: device?.device_role ?? "SERVER",
    asset_tag: device?.asset_tag ?? "",
    hostname: device?.hostname ?? "",
    mgmt_ip: device?.mgmt_ip ?? "",
    mgmt_mac: device?.mgmt_mac ?? "",
    firmware: device?.firmware ?? "",
    os_version: device?.os_version ?? "",
    purchase_date: device?.purchase_date ?? "",
    warranty_until: device?.warranty_until ?? "",
    psu_count: String(device?.psu_count ?? 1),
    power_nameplate_w: device?.power_nameplate_w != null ? String(device.power_nameplate_w) : "",
    power_max_w: device?.power_max_w != null ? String(device.power_max_w) : "",
    notes: device?.notes ?? "",
  });
  const [provenance, setProvenance] = useState<Provenance>({});
  const [error, setError] = useState<string | null>(null);

  const set = (field: string, value: string) => setForm((state) => ({ ...state, [field]: value }));

  const save = useApiMutation(
    (payload: { body: Record<string, unknown>; provenance: Provenance }) =>
      mutations.saveDevice(ciId, payload.body, payload.provenance),
    [keys.device(ciId), keys.ci(ciId), keys.ciHistory(ciId), ["devices", "list"]],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        onDone();
      },
      onError: (err) => {
        const message = describeError(err, t);
        setError(message);
        toast.error(message);
      },
    },
  );

  const submit = () => {
    const number = (field: string) => (form[field].trim() ? Number(form[field]) : null);
    save.mutate({
      body: {
        device_model_id: form.device_model_id || null,
        device_role: form.device_role,
        asset_tag: form.asset_tag.trim() || null,
        hostname: form.hostname.trim() || null,
        mgmt_ip: form.mgmt_ip.trim() || null,
        mgmt_mac: form.mgmt_mac.trim() || null,
        firmware: form.firmware.trim() || null,
        os_version: form.os_version.trim() || null,
        purchase_date: form.purchase_date || null,
        warranty_until: form.warranty_until || null,
        psu_count: Number(form.psu_count) || 0,
        power_nameplate_w: number("power_nameplate_w"),
        power_max_w: number("power_max_w"),
        notes: form.notes.trim() || null,
      },
      provenance,
    });
  };

  return (
    <Panel
      title={t("nav.devices")}
      actions={
        <>
          <Button size="sm" icon={<X size={13} />} onClick={onDone}>
            {t("app.cancel")}
          </Button>
          <Button size="sm" variant="primary" disabled={save.isPending} onClick={submit}>
            {t("devices.saveProfile")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("devices.model")}>
            <Select
              value={form.device_model_id}
              placeholder="—"
              onChange={(event) => set("device_model_id", event.target.value)}
              options={(models?.items ?? []).map((item) => ({
                value: item.id,
                label: `${item.manufacturer.name} ${item.model}`,
              }))}
            />
          </Field>
          <Field label={t("devices.role")}>
            <Select
              value={form.device_role}
              onChange={(event) => set("device_role", event.target.value)}
              options={(meta?.device_roles ?? []).map((value) => ({
                value,
                label: te("deviceRole", value),
              }))}
            />
          </Field>
          <Field label={t("devices.assetTag")}>
            <Input value={form.asset_tag} onChange={(event) => set("asset_tag", event.target.value)} />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("devices.hostname")}>
            <Input value={form.hostname} onChange={(event) => set("hostname", event.target.value)} />
          </Field>
          <Field label={t("devices.mgmtIp")}>
            <Input value={form.mgmt_ip} onChange={(event) => set("mgmt_ip", event.target.value)} />
          </Field>
          <Field label={t("devices.mgmtMac")}>
            <Input value={form.mgmt_mac} onChange={(event) => set("mgmt_mac", event.target.value)} />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={t("devices.firmware")}>
            <Input value={form.firmware} onChange={(event) => set("firmware", event.target.value)} />
          </Field>
          <Field label={t("devices.osVersion")}>
            <Input
              value={form.os_version}
              onChange={(event) => set("os_version", event.target.value)}
            />
          </Field>
          <Field label={t("devices.purchaseDate")}>
            <Input
              type="date"
              value={form.purchase_date}
              onChange={(event) => set("purchase_date", event.target.value)}
            />
          </Field>
          <Field label={t("devices.warrantyUntil")}>
            <Input
              type="date"
              value={form.warranty_until}
              onChange={(event) => set("warranty_until", event.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("catalog.psuCount")}>
            <Input
              type="number"
              min={0}
              value={form.psu_count}
              onChange={(event) => set("psu_count", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.powerNameplate")}>
            <Input
              type="number"
              min={0}
              value={form.power_nameplate_w}
              onChange={(event) => set("power_nameplate_w", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.powerMax")}>
            <Input
              type="number"
              min={0}
              value={form.power_max_w}
              onChange={(event) => set("power_max_w", event.target.value)}
            />
          </Field>
        </div>

        <Field label={t("ci.description")}>
          <Textarea rows={2} value={form.notes} onChange={(event) => set("notes", event.target.value)} />
        </Field>

        <div className="flex flex-col gap-2 border-t border-app pt-3">
          <ReasonField value={provenance} onChange={setProvenance} />
          <p className="text-xs text-muted">{t("devices.criticalFieldHint")}</p>
          <FormError message={error} />
        </div>
      </div>
    </Panel>
  );
}

export function CiNetworkTab({ ciId }: { ciId: string }) {
  const { t, te, locale } = useI18n();
  const { data: device, isPending, error } = useDevice(ciId);
  const { data: interfaces } = useDeviceInterfaces(device ? ciId : undefined);
  const { data: usage } = usePortUsage(device ? ciId : undefined);

  const [editing, setEditing] = useState(false);
  const [portDialog, setPortDialog] = useState<{ row: InterfaceRow | null } | null>(null);
  const [connectFrom, setConnectFrom] = useState<InterfaceRow | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<InterfaceRow | null>(null);
  const [deletingPort, setDeletingPort] = useState<InterfaceRow | null>(null);

  const invalidate = [
    keys.deviceInterfaces(ciId),
    keys.devicePorts(ciId),
    ["network", "connections"],
    keys.freePorts,
    keys.redundancy,
  ];

  const fromModel = useApiMutation(
    (_variables: void) => mutations.createInterfacesFromModel(ciId),
    invalidate,
    {
      onSuccess: () => toast.success(t("app.saved")),
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  const disconnect = useApiMutation(
    (payload: { id: string; provenance: Provenance }) =>
      mutations.deleteConnection(payload.id, payload.provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setDisconnecting(null);
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  const deletePort = useApiMutation(
    (payload: { id: string; provenance: Provenance }) =>
      mutations.deleteInterface(payload.id, payload.provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setDeletingPort(null);
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  if (isPending) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  const missingProfile = error instanceof ApiError && error.status === 404;
  if (missingProfile && !editing) {
    return (
      <Panel>
        <EmptyState
          title={t("devices.noProfile")}
          hint={t("devices.subtitle")}
          action={
            <Button variant="primary" icon={<Plus size={14} />} onClick={() => setEditing(true)}>
              {t("devices.createProfile")}
            </Button>
          }
        />
      </Panel>
    );
  }
  if (error && !missingProfile) {
    return (
      <Panel>
        <EmptyState title={describeError(error, t)} />
      </Panel>
    );
  }

  if (editing) {
    return (
      <ProfileForm ciId={ciId} device={device ?? null} onDone={() => setEditing(false)} />
    );
  }
  if (!device) return null;

  const columns: Array<Column<InterfaceRow>> = [
    {
      key: "name",
      header: t("network.port"),
      width: "11rem",
      render: (row) => (
        <span className="flex items-center gap-1.5">
          <span className="font-mono text-xs font-medium">{row.name}</span>
          {row.is_management && <Badge tone="accent">MGMT</Badge>}
          {!row.admin_enabled && <Badge>off</Badge>}
        </span>
      ),
    },
    {
      key: "type",
      header: t("network.type"),
      width: "8rem",
      render: (row) => <span className="text-xs text-muted">{te("interfaceType", row.interface_type)}</span>,
    },
    {
      key: "speed",
      header: t("network.speed"),
      width: "7rem",
      align: "right",
      render: (row) => (
        <span className="text-xs tabular-nums text-muted">{row.speed_mbps ?? "—"}</span>
      ),
    },
    {
      key: "mac",
      header: t("network.mac"),
      width: "11rem",
      render: (row) => <span className="font-mono text-xs text-muted">{row.mac ?? "—"}</span>,
    },
    {
      key: "addresses",
      header: t("network.addresses"),
      width: "11rem",
      render: (row) => (
        <span className="font-mono text-xs text-muted">{row.ip_addresses.join(", ") || "—"}</span>
      ),
    },
    {
      key: "vlans",
      header: t("network.vlans"),
      width: "9rem",
      render: (row) =>
        row.vlans.length ? (
          <span className="flex flex-wrap gap-1">
            {row.vlans.map((vlan) => (
              <Badge key={vlan.vlan_id} title={vlan.name}>
                {vlan.vid}
              </Badge>
            ))}
          </span>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "peer",
      header: t("network.peer"),
      render: (row) =>
        row.connection?.peer ? (
          <span className="flex items-center gap-1.5">
            <Link
              to={`/ci/${row.connection.peer.ci_id}`}
              className="truncate text-accent hover:underline"
            >
              {row.connection.peer.ci_name ?? "—"}
            </Link>
            <span className="font-mono text-xs text-muted">
              {row.connection.peer.interface_name}
            </span>
          </span>
        ) : (
          <span className="text-xs text-muted">—</span>
        ),
    },
    {
      key: "actions",
      header: "",
      width: "7rem",
      align: "right",
      render: (row) => (
        <span className="flex justify-end gap-0.5">
          {row.connection ? (
            <>
              <IconButton label={t("network.trace")} onClick={() => setTraceId(row.id)}>
                <Route size={13} />
              </IconButton>
              <IconButton label={t("network.disconnect")} onClick={() => setDisconnecting(row)}>
                <Unplug size={13} />
              </IconButton>
            </>
          ) : (
            <IconButton label={t("network.connect")} onClick={() => setConnectFrom(row)}>
              <Cable size={13} />
            </IconButton>
          )}
          <IconButton label={t("app.edit")} onClick={() => setPortDialog({ row })}>
            <Pencil size={13} />
          </IconButton>
          <IconButton label={t("app.delete")} onClick={() => setDeletingPort(row)}>
            <Trash2 size={13} />
          </IconButton>
        </span>
      ),
    },
  ];

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[1fr_18rem]">
        <Panel
          title={t("nav.devices")}
          actions={
            <Button size="sm" icon={<Pencil size={13} />} onClick={() => setEditing(true)}>
              {t("app.edit")}
            </Button>
          }
        >
          <KeyValue
            items={[
              {
                label: t("devices.model"),
                value: device.model
                  ? `${device.model.manufacturer.name} ${device.model.model}`
                  : "—",
              },
              { label: t("devices.role"), value: te("deviceRole", device.device_role) },
              { label: t("devices.hostname"), value: device.hostname ?? "—" },
              {
                label: t("devices.mgmtIp"),
                value: device.mgmt_ip ? (
                  <span className="font-mono text-xs">{device.mgmt_ip}</span>
                ) : (
                  "—"
                ),
              },
              {
                label: t("devices.mgmtMac"),
                value: device.mgmt_mac ? (
                  <span className="font-mono text-xs">{device.mgmt_mac}</span>
                ) : (
                  "—"
                ),
              },
              { label: t("devices.assetTag"), value: device.asset_tag ?? "—" },
              { label: t("devices.firmware"), value: device.firmware ?? "—" },
              { label: t("devices.osVersion"), value: device.os_version ?? "—" },
              {
                label: t("devices.purchaseDate"),
                value: formatDate(device.purchase_date, locale),
              },
              {
                label: t("devices.warrantyUntil"),
                value: formatDate(device.warranty_until, locale),
              },
              { label: t("catalog.psuCount"), value: device.psu_count },
              {
                label: t("catalog.powerNameplate"),
                value: device.power_nameplate_w ? `${device.power_nameplate_w} Вт` : "—",
              },
              {
                label: t("catalog.powerMax"),
                value: device.power_max_w ? `${device.power_max_w} Вт` : "—",
              },
            ]}
          />
        </Panel>

        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <Metric label={t("devices.portsTotal")} value={usage?.total ?? 0} />
          <Metric
            label={t("devices.portsFree")}
            value={usage?.free ?? 0}
            tone={usage && usage.total > 0 && usage.free === 0 ? "warn" : "default"}
          />
          <Metric label={t("devices.portsUsed")} value={usage?.used ?? 0} />
        </div>
      </div>

      <Panel
        title={t("network.interfaces")}
        bodyClassName="p-0"
        actions={
          <>
            {device.device_model_id && (
              <Button
                size="sm"
                disabled={fromModel.isPending}
                onClick={() => fromModel.mutate()}
              >
                {t("devices.fromModel")}
              </Button>
            )}
            <Button
              size="sm"
              variant="primary"
              icon={<Plus size={13} />}
              onClick={() => setPortDialog({ row: null })}
            >
              {t("devices.addPort")}
            </Button>
          </>
        }
      >
        <DataTable
          columns={columns}
          rows={interfaces ?? []}
          rowKey={(row) => row.id}
          emptyTitle={t("network.emptyPorts")}
          emptyHint={device.device_model_id ? t("devices.fromModel") : undefined}
        />
      </Panel>

      {portDialog && (
        <InterfaceDialog
          open
          ciId={ciId}
          row={portDialog.row}
          onClose={() => setPortDialog(null)}
        />
      )}

      <ConnectionDialog
        open={Boolean(connectFrom)}
        fromInterfaceId={connectFrom?.id}
        fromLabel={connectFrom?.name}
        onClose={() => setConnectFrom(null)}
      />

      <TraceDialog interfaceId={traceId} onClose={() => setTraceId(null)} />

      <ConfirmDialog
        open={Boolean(disconnecting)}
        title={t("network.disconnectConfirm")}
        confirmLabel={t("network.disconnect")}
        danger
        pending={disconnect.isPending}
        onCancel={() => setDisconnecting(null)}
        onConfirm={(provenance) =>
          disconnecting?.connection &&
          disconnect.mutate({ id: disconnecting.connection.id, provenance })
        }
      />

      <ConfirmDialog
        open={Boolean(deletingPort)}
        title={`${t("app.delete")}: ${deletingPort?.name ?? ""}`}
        confirmLabel={t("app.delete")}
        danger
        pending={deletePort.isPending}
        onCancel={() => setDeletingPort(null)}
        onConfirm={(provenance) =>
          deletingPort && deletePort.mutate({ id: deletingPort.id, provenance })
        }
      />
    </>
  );
}
