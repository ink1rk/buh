import { Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useDeviceModels, useDeviceParts } from "@/shared/api/queries";
import { Button, IconButton } from "@/shared/ui/Button";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { PlatformBoard } from "./PlatformBoard";

const CLASSES = ["CPU", "BOARD", "MEMORY", "DISK", "NIC", "HBA", "PSU"] as const;

export function DevicePartsPanel({ ciId }: { ciId: string }) {
  const { t, te } = useI18n();
  const { data } = useDeviceParts(ciId);
  const [kind, setKind] = useState<string>("CPU");
  const [modelId, setModelId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const { data: models } = useDeviceModels({
    limit: 500,
    offset: 0,
    component_class: kind,
  });

  const save = useApiMutation(
    (body: { component_model_id: string; quantity: number; slots?: string[] }) =>
      mutations.setDevicePart(ciId, body),
    [keys.deviceParts(ciId)],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setError(null);
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  const remove = useApiMutation(
    (partId: string) => mutations.deleteDevicePart(ciId, partId),
    [keys.deviceParts(ciId)],
    {
      onSuccess: () => toast.success(t("app.saved")),
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  function toggleSlot(name: string) {
    const items = data?.items ?? [];
    const owner = items.find((part) => (part.slots ?? []).includes(name));
    if (owner) {
      const next = (owner.slots ?? []).filter((slot) => slot !== name);
      if (next.length === 0) {
        remove.mutate(owner.id);
        return;
      }
      save.mutate({
        component_model_id: owner.component_model_id,
        quantity: next.length,
        slots: next,
      });
      return;
    }
    const expected = (data?.cpu_slot_names ?? []).includes(name) ? "CPU" : "MEMORY";
    if (kind !== expected || !modelId) {
      toast.error(t("devices.pickPart"));
      return;
    }
    const existing = items.find((part) => part.component_model_id === modelId);
    const next = [...(existing?.slots ?? []), name];
    save.mutate({ component_model_id: modelId, quantity: next.length, slots: next });
  }

  const capacity = [
    data?.cpu_sockets ? `${data.cpu_sockets}× ${data.cpu_socket ?? t("devices.parts")}` : "",
    data?.ram_slots ? `${data.ram_slots}× ${data.ram_type ?? "RAM"}` : "",
    data?.drive_bays ? `${data.drive_bays}× ${data.drive_form ?? ""}`.trim() : "",
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <Panel title={t("devices.parts")}>
      <PlatformBoard
        cpuNames={data?.cpu_slot_names ?? []}
        ramNames={data?.ram_slot_names ?? []}
        items={data?.items ?? []}
        onToggle={toggleSlot}
      />
      <p className="mb-3 text-xs text-muted">{capacity || t("devices.partsHint")}</p>
      <ul className="mb-3 flex flex-col gap-1">
        {(data?.items ?? []).length === 0 && (
          <li className="text-sm text-muted">{t("devices.noParts")}</li>
        )}
        {(data?.items ?? []).map((part) => (
          <li key={part.id} className="flex items-center gap-2 text-sm">
            <span className="w-36 shrink-0 text-muted">
              {te("componentClass", part.component.component_class)}
            </span>
            <span className="min-w-0 flex-1 truncate">
              {part.component.manufacturer.name} {part.component.model}
            </span>
            <span className="max-w-40 truncate text-right font-mono text-[10px] text-muted">
              {part.slots?.length ? part.slots.join(" ") : `× ${part.quantity}`}
            </span>
            <IconButton label={t("app.delete")} onClick={() => remove.mutate(part.id)}>
              <Trash2 size={13} />
            </IconButton>
          </li>
        ))}
      </ul>
      <div className="grid items-end gap-2 sm:grid-cols-[10rem_1fr_6rem_auto]">
        <Field label={t("catalog.componentClass")}>
          <Select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setModelId("");
            }}
            options={CLASSES.map((value) => ({ value, label: te("componentClass", value) }))}
          />
        </Field>
        <Field label={t("catalog.model")}>
          <Select
            value={modelId}
            placeholder="—"
            onChange={(event) => setModelId(event.target.value)}
            options={(models?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.manufacturer.name} ${item.model}`,
            }))}
          />
        </Field>
        <Field label={t("devices.partQuantity")}>
          <Input
            type="number"
            min={1}
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </Field>
        <Button
          variant="primary"
          disabled={!modelId || save.isPending}
          onClick={() =>
            save.mutate({
              component_model_id: modelId,
              quantity: Math.max(1, Number(quantity) || 1),
            })
          }
        >
          {t("devices.addPart")}
        </Button>
      </div>
      <FormError message={error} />
    </Panel>
  );
}
