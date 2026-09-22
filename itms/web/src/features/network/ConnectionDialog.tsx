import { useState } from "react";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useMeta, useRoutes } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Checkbox, Field, Input, Select } from "@/shared/ui/Field";
import { FormError } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ReasonField } from "../provenance/ReasonField";
import { PortPicker } from "./PortPicker";

export function ConnectionDialog({
  open,
  /** Порт, от которого тянут кабель: если задан, ближний конец не выбирается. */
  fromInterfaceId,
  fromLabel,
  onClose,
}: {
  open: boolean;
  fromInterfaceId?: string;
  fromLabel?: string;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: routes } = useRoutes();

  const [aEnd, setAEnd] = useState("");
  const [bEnd, setBEnd] = useState("");
  const [medium, setMedium] = useState("COPPER");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [label, setLabel] = useState("");
  const [length, setLength] = useState("");
  const [routeId, setRouteId] = useState("");
  const [redundant, setRedundant] = useState(false);
  const [group, setGroup] = useState("");
  const [provenance, setProvenance] = useState<Provenance>({});
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setAEnd("");
    setBEnd("");
    setLabel("");
    setLength("");
    setRedundant(false);
    setGroup("");
    setProvenance({});
    setError(null);
  };

  const create = useApiMutation(
    (payload: { body: Record<string, unknown>; provenance: Provenance }) =>
      mutations.createConnection(payload.body, payload.provenance),
    [["network", "connections"], ["devices"], keys.freePorts, keys.redundancy],
    {
      onSuccess: (result) => {
        if (result.warnings.length) {
          toast.info(t("network.warnings"), result.warnings.join("; "));
        } else {
          toast.success(t("app.saved"));
        }
        reset();
        onClose();
      },
      onError: (err) => {
        const message = describeError(err, t);
        setError(message);
        toast.error(message);
      },
    },
  );

  const a = fromInterfaceId ?? aEnd;
  const canSubmit = Boolean(a && bEnd && a !== bEnd);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("network.connect")}
      description={fromLabel}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!canSubmit || create.isPending}
            onClick={() =>
              create.mutate({
                body: {
                  a_interface_id: a,
                  b_interface_id: bEnd,
                  medium,
                  category: category || null,
                  status,
                  label: label.trim() || null,
                  length_m: length.trim() ? Number(length) : null,
                  route_id: routeId || null,
                  is_redundant: redundant,
                  redundancy_group: group.trim() || null,
                },
                provenance,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {!fromInterfaceId && (
          <PortPicker
            label={t("network.port")}
            value={aEnd}
            excludeInterfaceId={bEnd}
            onChange={setAEnd}
          />
        )}
        <PortPicker
          label={t("network.peer")}
          value={bEnd}
          excludeInterfaceId={a}
          onChange={setBEnd}
        />

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={t("network.medium")}>
            <Select
              value={medium}
              onChange={(event) => setMedium(event.target.value)}
              options={(meta?.cable_media ?? []).map((value) => ({
                value,
                label: te("cableMedium", value),
              }))}
            />
          </Field>
          <Field label={t("network.category")}>
            <Select
              value={category}
              placeholder="—"
              onChange={(event) => setCategory(event.target.value)}
              options={(meta?.cable_categories ?? []).map((value) => ({
                value,
                label: te("cableCategory", value),
              }))}
            />
          </Field>
          <Field label={t("network.status")}>
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              options={(meta?.connection_statuses ?? []).map((value) => ({
                value,
                label: te("connectionStatus", value),
              }))}
            />
          </Field>
          <Field label={t("network.length")}>
            <Input
              type="number"
              min={0}
              step="0.1"
              value={length}
              onChange={(event) => setLength(event.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("network.label")}>
            <Input value={label} onChange={(event) => setLabel(event.target.value)} />
          </Field>
          <Field label={t("network.route")}>
            <Select
              value={routeId}
              placeholder="—"
              onChange={(event) => setRouteId(event.target.value)}
              options={(routes ?? []).map((item) => ({ value: item.id, label: item.name }))}
            />
          </Field>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <Checkbox
            label={t("network.isRedundant")}
            className="pb-1.5"
            checked={redundant}
            onChange={(event) => setRedundant(event.target.checked)}
          />
          {redundant && (
            <Field label={t("network.redundancyGroup")} className="flex-1">
              <Input value={group} onChange={(event) => setGroup(event.target.value)} />
            </Field>
          )}
        </div>

        <div className="border-t border-app pt-3">
          <ReasonField value={provenance} onChange={setProvenance} />
        </div>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
