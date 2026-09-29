import { History, Pencil, X } from "lucide-react";
import { useState, type ReactNode } from "react";

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
import type { Ci } from "@/shared/api/types";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { FormError, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ProvenanceDialog } from "../provenance/ProvenanceDialog";
import { ReasonField } from "../provenance/ReasonField";

/** Поля, для которых бэкенд требует происхождение изменения. */
const CRITICAL_FIELDS = new Set(["status", "criticality", "location_id", "owner_employee_id"]);

interface Row {
  field: string;
  label: string;
  value: ReactNode;
}

function ReadRow({
  row,
  onProvenance,
}: {
  row: Row;
  onProvenance: (field: string, label: string) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="group grid grid-cols-[minmax(8rem,10rem)_1fr_1.75rem] items-start gap-x-3 py-1">
      <dt className="text-xs leading-6 text-muted">{row.label}</dt>
      <dd className="min-w-0 leading-6 break-words">{row.value}</dd>
      <IconButton
        label={t("ci.openProvenance")}
        className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
        onClick={() => onProvenance(row.field, row.label)}
      >
        <History size={13} />
      </IconButton>
    </div>
  );
}

export function CiOverviewTab({ ci }: { ci: Ci }) {
  const { t, te, locale } = useI18n();
  const { data: meta } = useMeta();
  const { data: locations } = useLocations();
  const { data: employees } = useEmployees();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [provenance, setProvenance] = useState<Provenance>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [inspect, setInspect] = useState<{ field: string; label: string } | null>(null);

  const update = useApiMutation(
    (payload: { body: Record<string, unknown>; provenance: Provenance }) =>
      mutations.updateCi(ci.id, payload.body, payload.provenance),
    [keys.ci(ci.id), keys.ciHistory(ci.id), ["ci", "list"], keys.dashboard],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setEditing(false);
        setDraft({});
        setProvenance({});
        setSaveError(null);
      },
      onError: (error) => {
        const message = describeError(error, t);
        setSaveError(message);
        toast.error(message);
      },
    },
  );

  const startEdit = () => {
    setDraft({
      name: ci.name,
      code: ci.code ?? "",
      status: ci.status,
      criticality: ci.criticality,
      environment: ci.environment,
      location_id: ci.location_id ?? "",
      owner_employee_id: ci.owner_employee_id ?? "",
      vendor: ci.vendor ?? "",
      model: ci.model ?? "",
      serial_number: ci.serial_number ?? "",
      inventory_number: ci.inventory_number ?? "",
      description: ci.description ?? "",
      tags: ci.tags.join(", "),
    });
    setSaveError(null);
    setEditing(true);
  };

  const set = (key: string, value: unknown) => setDraft((state) => ({ ...state, [key]: value }));

  const changedFields = Object.keys(draft).filter((key) => {
    const current = key === "tags" ? ci.tags.join(", ") : ((ci[key as keyof Ci] ?? "") as unknown);
    return draft[key] !== current;
  });
  const provenanceRequired = changedFields.some((field) => CRITICAL_FIELDS.has(field));

  const save = () => {
    const body: Record<string, unknown> = { version: ci.version };
    for (const key of changedFields) {
      if (key === "tags") {
        body.tags = String(draft.tags)
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean);
      } else {
        body[key] = draft[key] === "" ? null : draft[key];
      }
    }
    update.mutate({ body, provenance });
  };

  const allowedStatuses = meta?.ci_status_transitions[ci.status] ?? [];

  if (editing) {
    return (
      <Panel
        title={t("ci.overview")}
        actions={
          <>
            <Button size="sm" icon={<X size={13} />} onClick={() => setEditing(false)}>
              {t("app.cancel")}
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={update.isPending || !changedFields.length}
              onClick={save}
            >
              {t("app.save")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("ci.name")} required>
              <Input
                value={String(draft.name ?? "")}
                onChange={(event) => set("name", event.target.value)}
              />
            </Field>
            <Field label={t("ci.code")}>
              <Input
                value={String(draft.code ?? "")}
                onChange={(event) => set("code", event.target.value)}
              />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t("ci.status")} hint={t("ci.statusHint")}>
              <Select
                value={String(draft.status ?? "")}
                onChange={(event) => set("status", event.target.value)}
                options={[
                  { value: ci.status, label: te("ciStatus", ci.status) },
                  ...allowedStatuses.map((value) => ({
                    value,
                    label: te("ciStatus", value),
                  })),
                ]}
              />
            </Field>
            <Field label={t("ci.criticality")}>
              <Select
                value={String(draft.criticality ?? "")}
                onChange={(event) => set("criticality", event.target.value)}
                options={(meta?.criticalities ?? []).map((value) => ({
                  value,
                  label: te("criticality", value),
                }))}
              />
            </Field>
            <Field label={t("ci.environment")}>
              <Select
                value={String(draft.environment ?? "")}
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
                value={String(draft.location_id ?? "")}
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
                value={String(draft.owner_employee_id ?? "")}
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
              <Input
                value={String(draft.vendor ?? "")}
                onChange={(event) => set("vendor", event.target.value)}
              />
            </Field>
            <Field label={t("ci.model")}>
              <Input
                value={String(draft.model ?? "")}
                onChange={(event) => set("model", event.target.value)}
              />
            </Field>
            <Field label={t("ci.serial")}>
              <Input
                value={String(draft.serial_number ?? "")}
                onChange={(event) => set("serial_number", event.target.value)}
              />
            </Field>
            <Field label={t("ci.inventory")}>
              <Input
                value={String(draft.inventory_number ?? "")}
                onChange={(event) => set("inventory_number", event.target.value)}
              />
            </Field>
          </div>

          <Field label={t("ci.tags")} hint={t("ci.tagsHint")}>
            <Input
              value={String(draft.tags ?? "")}
              onChange={(event) => set("tags", event.target.value)}
            />
          </Field>

          <Field label={t("ci.description")}>
            <Textarea
              rows={4}
              value={String(draft.description ?? "")}
              onChange={(event) => set("description", event.target.value)}
            />
          </Field>

          <div className="flex flex-col gap-2 border-t border-app pt-3">
            <ReasonField
              value={provenance}
              onChange={setProvenance}
              required={provenanceRequired}
            />
            {provenanceRequired && (
              <p className="text-xs text-[rgb(var(--warn))]">{t("ci.criticalFieldHint")}</p>
            )}
            <FormError message={saveError} />
          </div>
        </div>
      </Panel>
    );
  }

  const rows: Row[] = [
    { field: "ci_type", label: t("ci.type"), value: te("ciType", ci.ci_type) },
    { field: "code", label: t("ci.code"), value: ci.code ?? "—" },
    {
      field: "status",
      label: t("ci.status"),
      value: <Badge tone={toneFor("ciStatus", ci.status)}>{te("ciStatus", ci.status)}</Badge>,
    },
    {
      field: "criticality",
      label: t("ci.criticality"),
      value: (
        <Badge tone={toneFor("criticality", ci.criticality)}>
          {te("criticality", ci.criticality)}
        </Badge>
      ),
    },
    { field: "environment", label: t("ci.environment"), value: te("environment", ci.environment) },
    { field: "location_id", label: t("ci.location"), value: ci.location?.path ?? "—" },
    {
      field: "owner_employee_id",
      label: t("ci.owner"),
      value:
        employees?.find((employee) => employee.id === ci.owner_employee_id)?.full_name ?? "—",
    },
    { field: "vendor", label: t("ci.vendor"), value: ci.vendor ?? "—" },
    { field: "model", label: t("ci.model"), value: ci.model ?? "—" },
    {
      field: "serial_number",
      label: t("ci.serial"),
      value: ci.serial_number ? <span className="font-mono text-xs">{ci.serial_number}</span> : "—",
    },
    { field: "inventory_number", label: t("ci.inventory"), value: ci.inventory_number ?? "—" },
    {
      field: "tags",
      label: t("ci.tags"),
      value: ci.tags.length ? (
        <span className="flex flex-wrap gap-1">
          {ci.tags.map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </span>
      ) : (
        "—"
      ),
    },
    { field: "description", label: t("ci.description"), value: ci.description ?? "—" },
  ];

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[1fr_18rem]">
        <Panel
          title={t("ci.overview")}
          actions={
            <Button size="sm" icon={<Pencil size={13} />} onClick={startEdit}>
              {t("app.edit")}
            </Button>
          }
        >
          <dl className="divide-y divide-[rgb(var(--border))]/60">
            {rows.map((row) => (
              <ReadRow
                key={row.field}
                row={row}
                onProvenance={(field, label) => setInspect({ field, label })}
              />
            ))}
          </dl>
        </Panel>

        <Panel title={t("ci.version")}>
          <dl className="flex flex-col gap-1.5 text-sm">
            <div className="flex justify-between gap-2">
              <dt className="text-xs text-muted">{t("ci.version")}</dt>
              <dd className="tabular-nums">{ci.version}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-xs text-muted">{t("ci.created_at")}</dt>
              <dd className="text-xs">{formatDateTime(ci.created_at, locale)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-xs text-muted">{t("ci.updated")}</dt>
              <dd className="text-xs">{formatDateTime(ci.updated_at, locale)}</dd>
            </div>
            {ci.archived_at && (
              <div className="flex justify-between gap-2">
                <dt className="text-xs text-muted">{t("ci.archived_at")}</dt>
                <dd className="text-xs">{formatDateTime(ci.archived_at, locale)}</dd>
              </div>
            )}
            {(ci.valid_from || ci.valid_to) && (
              <div className="flex justify-between gap-2">
                <dt className="text-xs text-muted">{t("ci.validity")}</dt>
                <dd className="text-xs">
                  {formatDate(ci.valid_from, locale)} — {formatDate(ci.valid_to, locale)}
                </dd>
              </div>
            )}
          </dl>
        </Panel>
      </div>

      {inspect && (
        <ProvenanceDialog
          ciId={ci.id}
          field={inspect.field}
          fieldLabel={inspect.label}
          onClose={() => setInspect(null)}
        />
      )}
    </>
  );
}
