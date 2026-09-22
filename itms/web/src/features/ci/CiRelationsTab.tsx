import { ArrowDownLeft, ArrowUpRight, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useCiRelated } from "@/shared/api/queries";
import type { DocumentLinkRef, RelatedItem } from "@/shared/api/types";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { EmptyState, Panel, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { RelationDialog } from "./RelationDialog";

function isDocumentGroup(key: string): boolean {
  return key === "documents";
}

export function CiRelationsTab({ ciId }: { ciId: string }) {
  const { t, te } = useI18n();
  const { data, isPending } = useCiRelated(ciId);
  const [addOpen, setAddOpen] = useState(false);

  const remove = useApiMutation(
    (relationId: string) => mutations.deleteRelation(relationId),
    [keys.ciRelated(ciId), keys.ciHistory(ciId)],
    { onError: (error) => toast.error(describeError(error, t)) },
  );

  if (isPending) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  const groups = Object.entries(data ?? {}).filter(
    ([key, items]) => !isDocumentGroup(key) && items.length > 0,
  ) as Array<[string, RelatedItem[]]>;

  const documents = (data?.documents ?? []) as DocumentLinkRef[];

  return (
    <>
      <Panel
        title={t("ci.related")}
        bodyClassName={groups.length ? "p-0" : undefined}
        actions={
          <Button size="sm" icon={<Plus size={13} />} onClick={() => setAddOpen(true)}>
            {t("ci.addRelation")}
          </Button>
        }
      >
        {!groups.length ? (
          <EmptyState title={t("ci.noRelations")} />
        ) : (
          <div className="divide-y divide-[rgb(var(--border))]">
            {groups.map(([group, items]) => (
              <section key={group}>
                <h3 className="surface-muted px-3 py-1 text-[0.7rem] font-medium tracking-wide text-muted uppercase">
                  {te("relationGroup", group)}
                </h3>
                <ul className="divide-y divide-[rgb(var(--border))]/60">
                  {items.map((item) => (
                    <li key={item.relation_id} className="group flex items-center gap-3 px-3 py-1.5">
                      {item.direction === "outgoing" ? (
                        <ArrowUpRight size={14} className="shrink-0 text-muted" />
                      ) : (
                        <ArrowDownLeft size={14} className="shrink-0 text-muted" />
                      )}
                      <span className="w-40 shrink-0 text-xs text-muted">
                        {te("relationType", item.rel_type)}
                      </span>
                      <Link
                        to={`/ci/${item.ci.id}`}
                        className="min-w-0 flex-1 truncate text-sm text-accent hover:underline"
                      >
                        {item.ci.name}
                        {item.ci.code && (
                          <span className="ml-1.5 font-mono text-xs text-muted">{item.ci.code}</span>
                        )}
                      </Link>
                      <Badge tone={toneFor("ciStatus", item.ci.status)}>
                        {te("ciStatus", item.ci.status)}
                      </Badge>
                      <IconButton
                        label={t("ci.removeRelation")}
                        className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                        onClick={() => remove.mutate(item.relation_id)}
                      >
                        <Trash2 size={13} />
                      </IconButton>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </Panel>

      {documents.length > 0 && (
        <Panel title={t("ci.documents")} bodyClassName="p-0">
          <ul className="divide-y divide-[rgb(var(--border))]/60">
            {documents.map((link) => (
              <li key={link.document_id} className="px-3 py-1.5 text-sm">
                <Link to={`/documents/${link.document_id}`} className="text-accent hover:underline">
                  {link.relation ?? link.document_id}
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <RelationDialog open={addOpen} sourceCiId={ciId} onClose={() => setAddOpen(false)} />
    </>
  );
}
