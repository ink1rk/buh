import { useState } from "react";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { Button } from "@/shared/ui/Button";
import { Field, Input, Textarea } from "@/shared/ui/Field";
import { Dialog } from "@/shared/ui/Dialog";

/**
 * Причина изменения и ссылки на проект/изменение/задачу. Бэкенд требует их для
 * критичных полей, но собирать их полезно всегда: через год объяснить правку
 * будет больше нечем.
 */
export function ReasonField({
  value,
  onChange,
  required,
}: {
  value: Provenance;
  onChange: (next: Provenance) => void;
  required?: boolean;
}) {
  const { t } = useI18n();
  const [advanced, setAdvanced] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <Field label={t("app.reason")} hint={t("app.reasonHint")} required={required}>
        <Textarea
          rows={2}
          value={value.reason ?? ""}
          onChange={(event) => onChange({ ...value, reason: event.target.value })}
        />
      </Field>

      {advanced ? (
        <div className="grid gap-2 sm:grid-cols-3">
          <Field label={t("ci.inProject")} hint="UUID">
            <Input
              value={value.projectId ?? ""}
              onChange={(event) => onChange({ ...value, projectId: event.target.value })}
            />
          </Field>
          <Field label={t("ci.inChange")} hint="UUID">
            <Input
              value={value.changeId ?? ""}
              onChange={(event) => onChange({ ...value, changeId: event.target.value })}
            />
          </Field>
          <Field label={t("ci.inTask")} hint="UUID">
            <Input
              value={value.taskId ?? ""}
              onChange={(event) => onChange({ ...value, taskId: event.target.value })}
            />
          </Field>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdvanced(true)}
          className="self-start text-xs text-accent hover:underline"
        >
          {t("app.linkToWork")}
        </button>
      )}
    </div>
  );
}

/** Подтверждение необратимого действия вместе со сбором причины. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  danger,
  pending,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  danger?: boolean;
  pending?: boolean;
  onCancel: () => void;
  onConfirm: (provenance: Provenance) => void;
}) {
  const { t } = useI18n();
  const [provenance, setProvenance] = useState<Provenance>({});

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      description={description}
      width="sm"
      footer={
        <>
          <Button onClick={onCancel}>{t("app.cancel")}</Button>
          <Button
            variant={danger ? "danger" : "primary"}
            disabled={pending}
            onClick={() => onConfirm(provenance)}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <ReasonField value={provenance} onChange={setProvenance} />
    </Dialog>
  );
}
