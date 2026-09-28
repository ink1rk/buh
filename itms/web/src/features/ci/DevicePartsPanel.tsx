import { Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useDeviceModels, useDeviceParts } from "@/shared/api/queries";
import { Button, IconButton } from "@/shared/ui/Button";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const CLASSES = ["CPU", "BOARD", "MEMORY", "DISK", "NIC", "HBA", "PSU"] as const;

export function DevicePartsPanel({ ciId }: { ciId: string }) {
  const { t, te } = useI18n();
  const { data } = useDeviceParts(ciId);
  const [kind, setKind] = useState<string>("CPU");
  const [modelId, setModelId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const { data: models } = useDeviceModels({
    limit: 200,
    offset: 0,
    component_class: kind,
  });

  const save = useApiMutation(
    (body: { component_model_id: string; quantity: number }) => mutations.setDevicePart(ciId, body),
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

  const capacity = [
    data?.cpu_sockets ? `${data.cpu_sockets}× ${data.cpu_socket ?? t("devices.parts")}` : "",
    data?.ram_slots ? `${data.ram_slots}× ${data.ram_type ?? "RAM"}` : "",
    data?.drive_bays ? `${data.drive_bays}× ${data.drive_form ?? ""}`.trim() : "",
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <Panel title={t("devices.parts")}>
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
            <span className="tabular-nums text-muted">× {part.quantity}</span>
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
