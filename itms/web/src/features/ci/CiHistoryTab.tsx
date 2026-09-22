import { useI18n } from "@/i18n";
import { useCiHistory } from "@/shared/api/queries";
import { formatAuditValue, formatDateTime } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { EmptyState, Panel, Spinner } from "@/shared/ui/Layout";

export function CiHistoryTab({ ciId }: { ciId: string }) {
  const { t, te, locale } = useI18n();
  const { data, isPending } = useCiHistory(ciId);

  if (isPending) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }
  if (!data?.length) return <Panel><EmptyState title={t("ci.noHistory")} /></Panel>;

  return (
    <Panel title={t("ci.history")} bodyClassName="p-0">
      <ol className="divide-y divide-[rgb(var(--border))]">
        {data.map((log) => (
          <li key={log.id} className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={toneFor("auditAction", log.action)}>{te("auditAction", log.action)}</Badge>
              <span className="text-xs text-muted">{formatDateTime(log.occurred_at, locale)}</span>
              <span className="text-xs">{log.actor_label ?? log.actor_kind}</span>
              {log.reason ? (
                <span className="text-xs text-muted">· {log.reason}</span>
              ) : (
                <span className="text-xs text-muted">· {t("audit.noOrigin")}</span>
              )}
            </div>

            {log.changes.length > 0 && (
              <ul className="mt-1.5 flex flex-col gap-0.5">
                {log.changes.map((change, index) => (
                  <li
                    key={index}
                    className="grid grid-cols-[minmax(8rem,10rem)_1fr] gap-x-3 text-xs"
                  >
                    <span className="text-muted">{change.field}</span>
                    <span className="min-w-0 break-words">
                      <span className="text-muted line-through">
                        {formatAuditValue(change.old_value)}
                      </span>
                      <span className="mx-1.5 text-muted">→</span>
                      <span>{formatAuditValue(change.new_value)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}

            {(log.project_id || log.change_id || log.task_id || log.document_id) && (
              <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[0.7rem] text-muted">
                {log.project_id && <span>{t("ci.inProject")}: {log.project_id.slice(0, 8)}</span>}
                {log.change_id && <span>{t("ci.inChange")}: {log.change_id.slice(0, 8)}</span>}
                {log.task_id && <span>{t("ci.inTask")}: {log.task_id.slice(0, 8)}</span>}
                {log.document_id && <span>{t("ci.inDocument")}: {log.document_id.slice(0, 8)}</span>}
              </div>
            )}
          </li>
        ))}
      </ol>
    </Panel>
  );
}
