import { useI18n } from "@/i18n";
import { useCiProvenance } from "@/shared/api/queries";
import { formatAuditValue, formatDateTime } from "@/shared/lib/format";
import { Dialog } from "@/shared/ui/Dialog";
import { EmptyState, Spinner } from "@/shared/ui/Layout";

/**
 * «Откуда взялось это значение»: цепочка изменений параметра с причиной и
 * ссылками на проект, изменение, задачу и документ.
 */
export function ProvenanceDialog({
  ciId,
  field,
  fieldLabel,
  onClose,
}: {
  ciId: string;
  field: string | null;
  fieldLabel: string;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const { data, isPending } = useCiProvenance(ciId, field);

  return (
    <Dialog
      open={Boolean(field)}
      onClose={onClose}
      title={t("ci.provenance")}
      description={fieldLabel}
      width="md"
    >
      {isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : !data?.length ? (
        <EmptyState title={t("ci.provenanceEmpty")} />
      ) : (
        <ol className="flex flex-col gap-3">
          {data.map((entry, index) => (
            <li key={index} className="border-l-2 border-app pl-3">
              <p className="text-xs text-muted">
                {formatDateTime(entry.occurred_at, locale)} · {entry.actor_label ?? entry.actor_kind}
              </p>
              <p className="mt-0.5 text-sm">
                <span className="text-muted line-through">{formatAuditValue(entry.old_value)}</span>
                <span className="mx-1.5 text-muted">→</span>
                <span className="font-medium">{formatAuditValue(entry.new_value)}</span>
              </p>
              {entry.reason && <p className="mt-1 text-xs">{entry.reason}</p>}
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[0.7rem] text-muted">
                {entry.project_id && <span>{t("ci.inProject")}: {entry.project_id.slice(0, 8)}</span>}
                {entry.change_id && <span>{t("ci.inChange")}: {entry.change_id.slice(0, 8)}</span>}
                {entry.task_id && <span>{t("ci.inTask")}: {entry.task_id.slice(0, 8)}</span>}
                {entry.document_id && (
                  <span>{t("ci.inDocument")}: {entry.document_id.slice(0, 8)}</span>
                )}
                {!entry.reason &&
                  !entry.project_id &&
                  !entry.change_id &&
                  !entry.task_id &&
                  !entry.document_id && <span>{t("audit.noOrigin")}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </Dialog>
  );
}
