import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useEmployees,
  useLocations,
  useMeta,
} from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { FormError } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ReasonField } from "../provenance/ReasonField";

interface FormState {
  ci_type: string;
  code: string;
  name: string;
  status: string;
  criticality: string;
  environment: string;
  location_id: string;
  owner_employee_id: string;
  vendor: string;
  model: string;
  serial_number: string;
  inventory_number: string;
  description: string;
  tags: string;
}

const EMPTY: FormState = {
  ci_type: "DEVICE",
  code: "",
  name: "",
  status: "ACTIVE",
  criticality: "MEDIUM",
  environment: "PROD",
  location_id: "",
  owner_employee_id: "",
  vendor: "",
  model: "",
  serial_number: "",
  inventory_number: "",
  description: "",
  tags: "",
};

export function CiCreateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data: meta } = useMeta();
  const { data: locations } = useLocations();
  const { data: employees } = useEmployees();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [provenance, setProvenance] = useState<Provenance>({});
  const [saveError, setSaveError] = useState<string | null>(null);

  const create = useApiMutation(
    (payload: { body: Record<string, unknown>; provenance: Provenance }) =>
      mutations.createCi(payload.body, payload.provenance),
    [["ci"], keys.dashboard],
    {
      onSuccess: (ci) => {
        toast.success(t("app.created"), ci.name);
        setForm(EMPTY);
        setProvenance({});
        setSaveError(null);
        onClose();
        navigate(`/ci/${ci.id}`);
      },
      onError: (error) => {
        const message = describeError(error, t);
        setSaveError(message);
        toast.error(message);
      },
    },
  );

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((state) => ({ ...state, [key]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate({
      body: {
        ci_type: form.ci_type,
        name: form.name.trim(),
        status: form.status,
        criticality: form.criticality,
        environment: form.environment,
        code: form.code.trim() || null,
        location_id: form.location_id || null,
        owner_employee_id: form.owner_employee_id || null,
        vendor: form.vendor.trim() || null,
        model: form.model.trim() || null,
        serial_number: form.serial_number.trim() || null,
        inventory_number: form.inventory_number.trim() || null,
        description: form.description.trim() || null,
        tags: form.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      },
      provenance,
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("ci.create")}
      width="lg"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            form="ci-create-form"
            type="submit"
            disabled={create.isPending || !form.name.trim()}
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <form id="ci-create-form" onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ci.type")} required>
            <Select
              value={form.ci_type}
              onChange={(event) => set("ci_type", event.target.value)}
              options={(meta?.ci_types ?? []).map((value) => ({
                value,
                label: te("ciType", value),
              }))}
            />
          </Field>
          <Field label={t("ci.code")} hint={t("ci.codeHint")}>
            <Input value={form.code} onChange={(event) => set("code", event.target.value)} />
          </Field>
        </div>

        <Field label={t("ci.name")} required>
          <Input
            value={form.name}
            autoFocus
            required
            onChange={(event) => set("name", event.target.value)}
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("ci.status")}>
            <Select
              value={form.status}
              onChange={(event) => set("status", event.target.value)}
              options={(meta?.ci_statuses ?? []).map((value) => ({
                value,
                label: te("ciStatus", value),
              }))}
            />
          </Field>
          <Field label={t("ci.criticality")}>
            <Select
              value={form.criticality}
              onChange={(event) => set("criticality", event.target.value)}
              options={(meta?.criticalities ?? []).map((value) => ({
                value,
                label: te("criticality", value),
              }))}
            />
          </Field>
          <Field label={t("ci.environment")}>
            <Select
              value={form.environment}
              onChange={(event) => set("environment", event.target.value)}
              options={(meta?.environments ?? []).map((value) => ({
                value,
                label: te("environment", value),
              }))}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ci.location")}>
            <Select
              value={form.location_id}
              placeholder="—"
              onChange={(event) => set("location_id", event.target.value)}
              options={(locations ?? []).map((location) => ({
                value: location.id,
                label: location.path,
              }))}
            />
          </Field>
          <Field label={t("ci.owner")}>
            <Select
              value={form.owner_employee_id}
              placeholder="—"
              onChange={(event) => set("owner_employee_id", event.target.value)}
              options={(employees ?? []).map((employee) => ({
                value: employee.id,
                label: employee.full_name,
              }))}
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={t("ci.vendor")}>
            <Input value={form.vendor} onChange={(event) => set("vendor", event.target.value)} />
          </Field>
          <Field label={t("ci.model")}>
            <Input value={form.model} onChange={(event) => set("model", event.target.value)} />
          </Field>
          <Field label={t("ci.serial")}>
            <Input
              value={form.serial_number}
              onChange={(event) => set("serial_number", event.target.value)}
            />
          </Field>
          <Field label={t("ci.inventory")}>
            <Input
              value={form.inventory_number}
              onChange={(event) => set("inventory_number", event.target.value)}
            />
          </Field>
        </div>

        <Field label={t("ci.tags")} hint={t("ci.tagsHint")}>
          <Input value={form.tags} onChange={(event) => set("tags", event.target.value)} />
        </Field>

        <Field label={t("ci.description")}>
          <Textarea
            rows={3}
            value={form.description}
            onChange={(event) => set("description", event.target.value)}
          />
        </Field>

        <div className="flex flex-col gap-2 border-t border-app pt-3">
          <ReasonField value={provenance} onChange={setProvenance} />
          <FormError message={saveError} />
        </div>
      </form>
    </Dialog>
  );
}
