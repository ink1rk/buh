import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useDeviceInterfaces,
  useMeta,
  useVlans,
} from "@/shared/api/queries";
import type { InterfaceRow } from "@/shared/api/types";
import { Button, IconButton } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Checkbox, Field, Input, Select } from "@/shared/ui/Field";
import { FormError } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ReasonField } from "../provenance/ReasonField";

interface VlanDraft {
  vlan_id: string;
  mode: string;
}

export function InterfaceDialog({
  open,
  ciId,
  row,
  onClose,
}: {
  open: boolean;
  ciId: string;
  /** null — создание нового порта. */
  row: InterfaceRow | null;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: vlans } = useVlans({});
  const { data: interfaces } = useDeviceInterfaces(ciId);

  const [form, setForm] = useState<Record<string, string | boolean>>({});
  const [vlanRows, setVlanRows] = useState<VlanDraft[]>([]);
  const [provenance, setProvenance] = useState<Provenance>({});
  const [error, setError] = useState<string | null>(null);
  const [initialisedFor, setInitialisedFor] = useState<string | null>(null);

  const key = row?.id ?? "new";
  if (open && initialisedFor !== key) {
    setInitialisedFor(key);
    setError(null);
    setProvenance({});
    setVlanRows((row?.vlans ?? []).map((item) => ({ vlan_id: item.vlan_id, mode: item.mode })));
    setForm({
      name: row?.name ?? "",
      interface_type: row?.interface_type ?? "RJ45",
      medium: row?.medium ?? "",
      speed_mbps: row?.speed_mbps != null ? String(row.speed_mbps) : "",
      mac: row?.mac ?? "",
      purpose: row?.purpose ?? "",
      description: row?.description ?? "",
      mtu: row?.mtu != null ? String(row.mtu) : "",
      panel_side: row?.panel_side ?? "",
      paired_interface_id: row?.paired_interface_id ?? "",
      admin_enabled: row?.admin_enabled ?? true,
      is_management: row?.is_management ?? false,
    });
  }

  const set = (field: string, value: string | boolean) =>
    setForm((state) => ({ ...state, [field]: value }));
  const text = (field: string) => String(form[field] ?? "");

  const onError = (err: unknown) => {
    const message = describeError(err, t);
    setError(message);
    toast.error(message);
  };

  const invalidate = [keys.deviceInterfaces(ciId), keys.devicePorts(ciId), keys.freePorts];

  const save = useApiMutation<unknown, { body: Record<string, unknown>; provenance: Provenance }>(
    (payload) =>
      row
        ? mutations.updateInterface(row.id, payload.body, payload.provenance)
        : mutations.createInterface(ciId, payload.body, payload.provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        onClose();
      },
      onError,
    },
  );

  const submit = () => {
    const body: Record<string, unknown> = {
      name: text("name").trim(),
      interface_type: form.interface_type,
      medium: text("medium") || null,
      speed_mbps: text("speed_mbps").trim() ? Number(form.speed_mbps) : null,
      mac: text("mac").trim() || null,
      purpose: text("purpose").trim() || null,
      description: text("description"),
      mtu: text("mtu").trim() ? Number(form.mtu) : null,
      panel_side: text("panel_side") || null,
      paired_interface_id: text("paired_interface_id") || null,
      admin_enabled: Boolean(form.admin_enabled),
      is_management: Boolean(form.is_management),
      vlans: vlanRows.filter((item) => item.vlan_id),
    };
    save.mutate({ body, provenance });
  };

  const pairCandidates = (interfaces ?? []).filter((item) => item.id !== row?.id);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={row ? row.name : t("devices.addPort")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!text("name").trim() || save.isPending}
            onClick={submit}
          >
            {t("app.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("network.port")} required>
            <Input value={text("name")} onChange={(event) => set("name", event.target.value)} />
          </Field>
          <Field label={t("network.type")}>
            <Select
              value={text("interface_type")}
              onChange={(event) => set("interface_type", event.target.value)}
              options={(meta?.interface_types ?? []).map((value) => ({
                value,
                label: te("interfaceType", value),
              }))}
            />
          </Field>
          <Field label={t("network.medium")}>
            <Select
              value={text("medium")}
              placeholder="—"
              onChange={(event) => set("medium", event.target.value)}
              options={(meta?.cable_media ?? []).map((value) => ({
                value,
                label: te("cableMedium", value),
              }))}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("network.speed")}>
            <Input
              type="number"
              min={0}
              value={text("speed_mbps")}
              onChange={(event) => set("speed_mbps", event.target.value)}
            />
          </Field>
          <Field label={t("network.mac")}>
            <Input
              value={text("mac")}
              placeholder="00:1a:2b:3c:4d:5e"
              onChange={(event) => set("mac", event.target.value)}
            />
          </Field>
          <Field label="MTU">
            <Input
              type="number"
              min={0}
              value={text("mtu")}
              onChange={(event) => set("mtu", event.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("network.panelSide")}>
            <Select
              value={text("panel_side")}
              placeholder="—"
              onChange={(event) => set("panel_side", event.target.value)}
              options={(meta?.panel_sides ?? []).map((value) => ({
                value,
                label: te("panelSide", value),
              }))}
            />
          </Field>
          <Field label={t("network.pairedPort")} hint={t("network.pairedHint")}>
            <Select
              value={text("paired_interface_id")}
              placeholder="—"
              onChange={(event) => set("paired_interface_id", event.target.value)}
              options={pairCandidates.map((item) => ({ value: item.id, label: item.name }))}
            />
          </Field>
        </div>

        <Field label={t("ipam.purpose")}>
          <Input value={text("purpose")} onChange={(event) => set("purpose", event.target.value)} />
        </Field>

        <div className="flex gap-4">
          <Checkbox
            label={t("network.adminEnabled")}
            checked={Boolean(form.admin_enabled)}
            onChange={(event) => set("admin_enabled", event.target.checked)}
          />
          <Checkbox
            label={t("network.management")}
            checked={Boolean(form.is_management)}
            onChange={(event) => set("is_management", event.target.checked)}
          />
        </div>

        <section className="flex flex-col gap-2 border-t border-app pt-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("network.vlans")}</h3>
            <Button
              size="sm"
              icon={<Plus size={13} />}
              onClick={() => setVlanRows((state) => [...state, { vlan_id: "", mode: "ACCESS" }])}
            >
              {t("app.create")}
            </Button>
          </div>
          {vlanRows.map((item, index) => (
            <div key={index} className="grid grid-cols-[1fr_9rem_2rem] items-center gap-2">
              <Select
                value={item.vlan_id}
                placeholder={t("app.nothingSelected")}
                onChange={(event) =>
                  setVlanRows((state) =>
                    state.map((row2, i) =>
                      i === index ? { ...row2, vlan_id: event.target.value } : row2,
                    ),
                  )
                }
                options={(vlans ?? []).map((vlan) => ({
                  value: vlan.id,
                  label: `${vlan.vid} — ${vlan.name}`,
                }))}
              />
              <Select
                value={item.mode}
                onChange={(event) =>
                  setVlanRows((state) =>
                    state.map((row2, i) => (i === index ? { ...row2, mode: event.target.value } : row2)),
                  )
                }
                options={(meta?.vlan_modes ?? []).map((value) => ({
                  value,
                  label: te("vlanMode", value),
                }))}
              />
              <IconButton
                label={t("app.delete")}
                onClick={() => setVlanRows((state) => state.filter((_, i) => i !== index))}
              >
                <Trash2 size={13} />
              </IconButton>
            </div>
          ))}
        </section>

        <div className="border-t border-app pt-3">
          <ReasonField value={provenance} onChange={setProvenance} />
        </div>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
