import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useManufacturers, useMeta } from "@/shared/api/queries";
import type { DeviceModel } from "@/shared/api/types";
import { Button, IconButton } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { FormError } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

interface TemplateDraft {
  name_pattern: string;
  count: number;
  start_index: number;
  interface_type: string;
  speed_mbps: string;
  poe_capable: boolean;
}

const EMPTY_TEMPLATE: TemplateDraft = {
  name_pattern: "",
  count: 1,
  start_index: 1,
  interface_type: "RJ45",
  speed_mbps: "",
  poe_capable: false,
};

/** Разворачивает маску так же, как это сделает бэкенд: чтобы счёт портов был виден до сохранения. */
function previewNames(draft: TemplateDraft): string[] {
  if (!draft.name_pattern.includes("{n}")) return [];
  const names: string[] = [];
  for (let index = 0; index < Math.min(draft.count, 4); index += 1) {
    names.push(draft.name_pattern.replace("{n}", String(draft.start_index + index)));
  }
  return names;
}

function numberOrNull(value: string): number | null {
  const parsed = Number(value);
  return value.trim() === "" || Number.isNaN(parsed) ? null : parsed;
}

export function ModelDialog({
  open,
  model,
  onClose,
}: {
  open: boolean;
  /** null — создание новой модели, объект — редактирование существующей. */
  model: DeviceModel | null;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: manufacturers } = useManufacturers();

  const [form, setForm] = useState<Record<string, string | boolean>>({});
  const [drafts, setDrafts] = useState<TemplateDraft[]>([]);
  const [template, setTemplate] = useState<TemplateDraft>(EMPTY_TEMPLATE);
  const [error, setError] = useState<string | null>(null);
  const [initialisedFor, setInitialisedFor] = useState<string | null>(null);

  const key = model?.id ?? "new";
  if (open && initialisedFor !== key) {
    setInitialisedFor(key);
    setError(null);
    setDrafts([]);
    setTemplate(EMPTY_TEMPLATE);
    setForm({
      manufacturer_id: model?.manufacturer_id ?? "",
      model: model?.model ?? "",
      part_number: model?.part_number ?? "",
      default_role: model?.default_role ?? "SERVER",
      u_height: String(model?.u_height ?? 1),
      is_full_depth: model?.is_full_depth ?? true,
      depth_mm: model?.depth_mm != null ? String(model.depth_mm) : "",
      weight_kg: model?.weight_kg != null ? String(model.weight_kg) : "",
      psu_count: String(model?.psu_count ?? 1),
      power_nameplate_w: model?.power_nameplate_w != null ? String(model.power_nameplate_w) : "",
      power_max_w: model?.power_max_w != null ? String(model.power_max_w) : "",
      airflow: model?.airflow ?? "",
      notes: model?.notes ?? "",
    });
  }

  const set = (field: string, value: string | boolean) =>
    setForm((state) => ({ ...state, [field]: value }));
  const text = (field: string) => String(form[field] ?? "");

  const invalidate = [["catalog", "models"], keys.manufacturers];
  const onError = (err: unknown) => {
    const message = describeError(err, t);
    setError(message);
    toast.error(message);
  };

  const save = useApiMutation(
    (body: Record<string, unknown>) =>
      model ? mutations.updateModel(model.id, body) : mutations.createModel(body),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        onClose();
      },
      onError,
    },
  );

  const addTemplate = useApiMutation(
    (body: Record<string, unknown>) => mutations.addPortTemplate(model?.id ?? "", body),
    invalidate,
    {
      onSuccess: () => setTemplate(EMPTY_TEMPLATE),
      onError,
    },
  );

  const removeTemplate = useApiMutation(
    (templateId: string) => mutations.deletePortTemplate(templateId),
    invalidate,
    { onError },
  );

  const templatePayload = (draft: TemplateDraft) => ({
    name_pattern: draft.name_pattern.trim(),
    count: Number(draft.count) || 1,
    start_index: Number(draft.start_index) || 0,
    interface_type: draft.interface_type,
    speed_mbps: numberOrNull(draft.speed_mbps),
    poe_capable: draft.poe_capable,
  });

  const submit = () => {
    const body: Record<string, unknown> = {
      manufacturer_id: form.manufacturer_id,
      model: text("model").trim(),
      part_number: text("part_number").trim() || null,
      default_role: form.default_role,
      u_height: Number(form.u_height) || 1,
      is_full_depth: Boolean(form.is_full_depth),
      depth_mm: numberOrNull(text("depth_mm")),
      weight_kg: numberOrNull(text("weight_kg")),
      psu_count: Number(form.psu_count) || 0,
      power_nameplate_w: numberOrNull(text("power_nameplate_w")),
      power_max_w: numberOrNull(text("power_max_w")),
      airflow: text("airflow").trim() || null,
      notes: text("notes").trim() || null,
    };
    if (!model) body.port_templates = drafts.map(templatePayload);
    save.mutate(body);
  };

  const canSubmit = Boolean(form.manufacturer_id) && text("model").trim().length > 0;
  const preview = previewNames(template);
  const interfaceTypes = (meta?.interface_types ?? []).map((value) => ({
    value,
    label: te("interfaceType", value),
  }));

  const templateEditor = (
    <div className="grid items-end gap-2 sm:grid-cols-[1fr_5rem_5rem_9rem_7rem_auto_auto]">
      <Field label={t("catalog.namePattern")}>
        <Input
          value={template.name_pattern}
          placeholder="Gi1/0/{n}"
          onChange={(event) => setTemplate({ ...template, name_pattern: event.target.value })}
        />
      </Field>
      <Field label={t("catalog.count")}>
        <Input
          type="number"
          min={1}
          value={template.count}
          onChange={(event) => setTemplate({ ...template, count: Number(event.target.value) })}
        />
      </Field>
      <Field label={t("catalog.startIndex")}>
        <Input
          type="number"
          min={0}
          value={template.start_index}
          onChange={(event) => setTemplate({ ...template, start_index: Number(event.target.value) })}
        />
      </Field>
      <Field label={t("network.type")}>
        <Select
          value={template.interface_type}
          options={interfaceTypes}
          onChange={(event) => setTemplate({ ...template, interface_type: event.target.value })}
        />
      </Field>
      <Field label={t("catalog.speed")}>
        <Input
          type="number"
          min={0}
          value={template.speed_mbps}
          onChange={(event) => setTemplate({ ...template, speed_mbps: event.target.value })}
        />
      </Field>
      <Checkbox
        label={t("catalog.poe")}
        className="pb-1.5"
        checked={template.poe_capable}
        onChange={(event) => setTemplate({ ...template, poe_capable: event.target.checked })}
      />
      <Button
        size="sm"
        className="mb-0.5"
        icon={<Plus size={13} />}
        disabled={!template.name_pattern.trim() || addTemplate.isPending}
        onClick={() => {
          if (model) addTemplate.mutate(templatePayload(template));
          else {
            setDrafts((state) => [...state, template]);
            setTemplate(EMPTY_TEMPLATE);
          }
        }}
      >
        {t("catalog.addTemplate")}
      </Button>
    </div>
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="lg"
      title={model ? `${model.manufacturer.name} ${model.model}` : t("catalog.addModel")}
      description={t("catalog.subtitle")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!canSubmit || save.isPending}
            onClick={submit}
          >
            {t("app.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("catalog.manufacturer")} required>
            <Select
              value={text("manufacturer_id")}
              placeholder="—"
              onChange={(event) => set("manufacturer_id", event.target.value)}
              options={(manufacturers ?? []).map((item) => ({ value: item.id, label: item.name }))}
            />
          </Field>
          <Field label={t("catalog.model")} required>
            <Input value={text("model")} onChange={(event) => set("model", event.target.value)} />
          </Field>
          <Field label={t("catalog.partNumber")}>
            <Input
              value={text("part_number")}
              onChange={(event) => set("part_number", event.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={t("catalog.defaultRole")}>
            <Select
              value={text("default_role")}
              onChange={(event) => set("default_role", event.target.value)}
              options={(meta?.device_roles ?? []).map((value) => ({
                value,
                label: te("deviceRole", value),
              }))}
            />
          </Field>
          <Field label={t("catalog.uHeight")}>
            <Input
              type="number"
              step="0.5"
              min={0}
              value={text("u_height")}
              onChange={(event) => set("u_height", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.depth")}>
            <Input
              type="number"
              min={0}
              value={text("depth_mm")}
              onChange={(event) => set("depth_mm", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.weight")}>
            <Input
              type="number"
              step="0.1"
              min={0}
              value={text("weight_kg")}
              onChange={(event) => set("weight_kg", event.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={t("catalog.psuCount")}>
            <Input
              type="number"
              min={0}
              value={text("psu_count")}
              onChange={(event) => set("psu_count", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.powerNameplate")}>
            <Input
              type="number"
              min={0}
              value={text("power_nameplate_w")}
              onChange={(event) => set("power_nameplate_w", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.powerMax")}>
            <Input
              type="number"
              min={0}
              value={text("power_max_w")}
              onChange={(event) => set("power_max_w", event.target.value)}
            />
          </Field>
          <Field label={t("catalog.airflow")}>
            <Input value={text("airflow")} onChange={(event) => set("airflow", event.target.value)} />
          </Field>
        </div>

        <Checkbox
          label={t("catalog.fullDepth")}
          checked={Boolean(form.is_full_depth)}
          onChange={(event) => set("is_full_depth", event.target.checked)}
        />

        <Field label={t("ci.description")}>
          <Textarea rows={2} value={text("notes")} onChange={(event) => set("notes", event.target.value)} />
        </Field>

        <section className="flex flex-col gap-2 border-t border-app pt-3">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("catalog.portTemplates")}</h3>
            <p className="text-xs text-muted">{t("catalog.templateHint")}</p>
          </div>

          {(model?.port_templates.length ?? 0) > 0 && (
            <ul className="divide-y divide-[rgb(var(--border))]/60 rounded border border-app">
              {model?.port_templates.map((item) => (
                <li key={item.id} className="flex items-center gap-3 px-2.5 py-1.5 text-sm">
                  <span className="font-mono text-xs">{item.name_pattern}</span>
                  <span className="text-xs text-muted">
                    ×{item.count} · {te("interfaceType", item.interface_type)}
                    {item.speed_mbps ? ` · ${item.speed_mbps} Мбит/с` : ""}
                    {item.poe_capable ? " · PoE" : ""}
                  </span>
                  <IconButton
                    label={t("app.delete")}
                    className="ml-auto"
                    onClick={() => removeTemplate.mutate(item.id)}
                  >
                    <Trash2 size={13} />
                  </IconButton>
                </li>
              ))}
            </ul>
          )}

          {drafts.length > 0 && (
            <ul className="divide-y divide-[rgb(var(--border))]/60 rounded border border-app">
              {drafts.map((item, index) => (
                <li key={index} className="flex items-center gap-3 px-2.5 py-1.5 text-sm">
                  <span className="font-mono text-xs">{item.name_pattern}</span>
                  <span className="text-xs text-muted">
                    ×{item.count} · {te("interfaceType", item.interface_type)}
                  </span>
                  <IconButton
                    label={t("app.delete")}
                    className="ml-auto"
                    onClick={() => setDrafts((state) => state.filter((_, i) => i !== index))}
                  >
                    <Trash2 size={13} />
                  </IconButton>
                </li>
              ))}
            </ul>
          )}

          {templateEditor}
          {preview.length > 0 && (
            <p className="font-mono text-xs text-muted">
              {preview.join(", ")}
              {template.count > preview.length ? ` … ×${template.count}` : ""}
            </p>
          )}
        </section>

        <FormError message={error} />
      </div>
    </Dialog>
  );
}
