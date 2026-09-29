import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useImportJob, useMeta } from "@/shared/api/queries";
import type { ImportJob } from "@/shared/api/types";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Field, Select } from "@/shared/ui/Field";
import { EmptyState, Metric, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const IMPORT_FIELD_LABEL: Record<string, string> = {
  code: "Код",
  name: "Наименование",
  ci_type: "Тип объекта",
  status: "Статус",
  criticality: "Критичность",
  environment: "Контур",
  location: "Размещение",
  owner: "Ответственный",
  vendor: "Производитель",
  model: "Модель",
  serial_number: "Серийный номер",
  inventory_number: "Инвентарный номер",
  description: "Описание",
  tags: "Теги",
  location_type: "Тип размещения",
  parent: "Входит в",
  address: "Адрес",
  full_name: "ФИО",
  position: "Должность",
  email: "Почта",
  phone: "Телефон",
  telegram: "Telegram",
  department: "Отдел",
  support_line: "Линия поддержки",
};

function MappingTable({
  job,
  fields,
  required,
  onChange,
  disabled,
}: {
  job: ImportJob;
  fields: string[];
  required: string[];
  onChange: (mapping: Record<string, string>) => void;
  disabled: boolean;
}) {
  const { t } = useI18n();
  const mapped = new Set(Object.values(job.mapping));

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-app text-left">
          <th className="px-2.5 py-1.5 text-xs font-medium text-muted">{t("imports.column")}</th>
          <th className="px-2.5 py-1.5 text-xs font-medium text-muted">{t("imports.field")}</th>
        </tr>
      </thead>
      <tbody>
        {job.columns.map((column) => (
          <tr key={column} className="border-b border-app/60">
            <td className="px-2.5 py-1.5 font-mono text-xs">{column}</td>
            <td className="px-2.5 py-1.5">
              <Select
                disabled={disabled}
                value={job.mapping[column] ?? ""}
                placeholder={t("imports.skip")}
                className="w-64"
                onChange={(event) => {
                  const next = { ...job.mapping };
                  if (event.target.value) next[column] = event.target.value;
                  else delete next[column];
                  onChange(next);
                }}
                options={fields.map((field) => ({
                  value: field,
                  label: `${IMPORT_FIELD_LABEL[field] ?? field}${required.includes(field) ? " *" : ""}`,
                  disabled: mapped.has(field) && job.mapping[column] !== field,
                }))}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ImportPage() {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();

  const [target, setTarget] = useState("CI");
  const [jobId, setJobId] = useState<string | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  const { data: job } = useImportJob(jobId);

  useEffect(() => {
    if (job) setMapping(job.mapping);
  }, [job]);

  const upload = useApiMutation(
    (payload: { target: string; file: File }) =>
      mutations.createImport(payload.target, payload.file),
    [],
    {
      onSuccess: (created) => setJobId(created.id),
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const jobKey = keys.importJob(jobId ?? "");

  const saveMapping = useApiMutation(
    (next: Record<string, string>) => mutations.updateImportMapping(jobId ?? "", next),
    [],
    { onError: (error) => toast.error(describeError(error, t)) },
  );

  const validate = useApiMutation(() => mutations.validateImport(jobId ?? ""), [jobKey], {
    onSuccess: () => toast.info(t("imports.validated")),
    onError: (error) => toast.error(describeError(error, t)),
  });

  const apply = useApiMutation(
    () => mutations.applyImport(jobId ?? ""),
    [jobKey, ["ci"], keys.locations, keys.locationTree, keys.employees, keys.dashboard],
    {
      onSuccess: (applied) =>
        toast.success(t("imports.applied"), `${applied.rows_created} / ${applied.rows_updated}`),
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const fields = meta?.import_fields[target] ?? [];
  const required = meta?.import_required_fields[target] ?? [];
  const applied = job?.status === "APPLIED";

  return (
    <>
      <PageHeader title={t("imports.title")} subtitle={t("imports.subtitle")} />

      <Panel title={t("imports.file")}>
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("imports.target")} className="w-56">
            <Select
              value={target}
              disabled={Boolean(jobId)}
              onChange={(event) => setTarget(event.target.value)}
              options={(meta?.import_targets ?? []).map((value) => ({
                value,
                label: te("importTarget", value),
              }))}
            />
          </Field>

          <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border border-app px-3 text-sm hover:bg-[rgb(var(--surface-muted))]">
            <Upload size={14} />
            {t("imports.upload")}
            <input
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate({ target, file });
                event.target.value = "";
              }}
            />
          </label>

          {jobId && (
            <Button
              variant="ghost"
              onClick={() => {
                setJobId(null);
                setMapping({});
              }}
            >
              {t("app.reset")}
            </Button>
          )}

          <p className="ml-auto max-w-md text-xs text-muted">{t("imports.hint")}</p>
        </div>
      </Panel>

      {!job ? (
        <Panel>
          <EmptyState
            title={t("imports.noJob")}
            hint={t("imports.hint")}
            action={<FileSpreadsheet size={20} className="mt-2 text-muted" />}
          />
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric label={t("imports.rowsTotal")} value={job.rows_total} />
            <Metric label={t("imports.rowsValid")} value={job.rows_valid} />
            <Metric
              label={t("imports.rowsInvalid")}
              value={job.rows_invalid}
              tone={job.rows_invalid ? "danger" : "default"}
            />
            <Metric label={t("imports.created")} value={job.rows_created} />
            <Metric label={t("imports.updated")} value={job.rows_updated} />
          </div>

          <Panel
            title={t("imports.mapping")}
            bodyClassName="p-0"
            actions={
              <>
                <Badge tone={applied ? "ok" : "neutral"}>{job.status}</Badge>
                <Button
                  size="sm"
                  disabled={applied || validate.isPending}
                  onClick={async () => {
                    await saveMapping.mutateAsync(mapping);
                    validate.mutate(undefined);
                  }}
                >
                  {t("imports.validate")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  icon={<CheckCircle2 size={13} />}
                  disabled={applied || !job.rows_valid || apply.isPending}
                  onClick={() => apply.mutate(undefined)}
                >
                  {t("imports.apply")}
                </Button>
              </>
            }
          >
            <MappingTable
              job={{ ...job, mapping }}
              fields={fields}
              required={required}
              disabled={applied}
              onChange={setMapping}
            />
          </Panel>

          {job.errors.length > 0 && (
            <Panel title={`${t("imports.errors")} (${job.errors.length})`} bodyClassName="p-0">
              <ul className="max-h-72 divide-y divide-[rgb(var(--border))]/60 overflow-y-auto">
                {job.errors.map((item) => (
                  <li key={item.row} className="flex gap-3 px-3 py-1.5 text-xs">
                    <span className="w-20 shrink-0 text-muted">
                      {t("imports.row")} {item.row}
                    </span>
                    <span className="text-[rgb(var(--danger))]">{item.errors.join("; ")}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {job.preview.length > 0 && (
            <Panel title={t("imports.preview")} bodyClassName="overflow-x-auto p-0">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-app text-left">
                    {job.columns.map((column) => (
                      <th key={column} className="px-2.5 py-1.5 font-medium whitespace-nowrap text-muted">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {job.preview.map((row, index) => (
                    <tr key={index} className="border-b border-app/60">
                      {job.columns.map((column) => (
                        <td key={column} className="px-2.5 py-1 whitespace-nowrap">
                          {String(row[column] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </>
      )}
    </>
  );
}
