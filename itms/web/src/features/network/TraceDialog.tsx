import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useTrace } from "@/shared/api/queries";
import { Badge } from "@/shared/ui/Badge";
import { Dialog } from "@/shared/ui/Dialog";
import { EmptyState, Spinner } from "@/shared/ui/Layout";

export function TraceDialog({
  interfaceId,
  onClose,
}: {
  interfaceId: string | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { data, isPending } = useTrace(interfaceId);

  return (
    <Dialog open={Boolean(interfaceId)} onClose={onClose} width="md" title={t("network.traceTitle")}>
      {isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : !data || !data.segments.length ? (
        <EmptyState title={t("network.traceEmpty")} />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Link to={`/ci/${data.start.ci_id}`} className="text-accent hover:underline">
              {data.start.ci_name ?? data.start.ci_id}
            </Link>
            <span className="font-mono text-xs text-muted">{data.start.interface_name}</span>
            <ArrowRight size={14} className="text-muted" />
            {data.endpoint ? (
              <>
                <Link to={`/ci/${data.endpoint.ci_id}`} className="text-accent hover:underline">
                  {data.endpoint.ci_name ?? data.endpoint.ci_id}
                </Link>
                <span className="font-mono text-xs text-muted">
                  {data.endpoint.interface_name}
                </span>
              </>
            ) : (
              <span className="text-muted">—</span>
            )}
          </div>

          {data.is_direct && <Badge tone="ok">{t("network.traceDirect")}</Badge>}

          {data.passed_through.length > 0 && (
            <div>
              <p className="text-xs text-muted">{t("network.traceThrough")}</p>
              <ul className="mt-1 flex flex-col gap-1">
                {data.passed_through.map((item) => (
                  <li key={item.ci_id} className="text-sm">
                    <Link to={`/ci/${item.ci_id}`} className="text-accent hover:underline">
                      {item.ci_name ?? item.ci_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <p className="text-xs text-muted">{t("network.connections")}</p>
            <ul className="mt-1 divide-y divide-[rgb(var(--border))]/60 rounded border border-app">
              {data.segments.map((segment) => (
                <li
                  key={segment.connection_id}
                  className="flex items-center justify-between gap-3 px-2.5 py-1.5 text-sm"
                >
                  <span className="font-mono text-xs">{segment.label ?? "—"}</span>
                  <span className="tabular-nums text-xs text-muted">
                    {segment.length_m != null ? `${segment.length_m} м` : "—"}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-sm">
            <span className="text-xs text-muted">{t("network.traceLength")}: </span>
            <span className="tabular-nums">
              {data.total_length_m != null ? `${data.total_length_m} м` : "—"}
            </span>
          </p>
        </div>
      )}
    </Dialog>
  );
}
