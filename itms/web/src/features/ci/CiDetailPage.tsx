import { Archive, ArchiveRestore, ChevronLeft, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useCi,
  useCiDocuments,
  useCiRelated,
} from "@/shared/api/queries";
import { useUiStore } from "@/shared/store/ui";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { EmptyState, Panel, Spinner } from "@/shared/ui/Layout";
import { Tabs } from "@/shared/ui/Tabs";
import { toast } from "@/shared/ui/toast";

import { ConfirmDialog } from "../provenance/ReasonField";
import { CiHistoryTab } from "./CiHistoryTab";
import { CiOverviewTab } from "./CiOverviewTab";
import { CiRelationsTab } from "./CiRelationsTab";

type Tab = "overview" | "related" | "documents" | "history";
type PendingAction = "archive" | "restore" | "delete" | null;

export function CiDetailPage() {
  const { t, te } = useI18n();
  const { ciId = "" } = useParams();
  const navigate = useNavigate();
  const pushRecent = useUiStore((state) => state.pushRecent);

  const [tab, setTab] = useState<Tab>("overview");
  const [action, setAction] = useState<PendingAction>(null);

  const { data: ci, isPending, isError, error } = useCi(ciId);
  const { data: related } = useCiRelated(ciId);
  const { data: documents } = useCiDocuments(ciId);

  useEffect(() => {
    if (ci) pushRecent({ id: ci.id, title: ci.name, path: `/ci/${ci.id}` });
  }, [ci, pushRecent]);

  const invalidate = [keys.ci(ciId), keys.ciHistory(ciId), ["ci", "list"], keys.dashboard];

  const archive = useApiMutation(
    (provenance: Provenance) => mutations.archiveCi(ciId, provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setAction(null);
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  const restore = useApiMutation(
    (provenance: Provenance) => mutations.restoreCi(ciId, provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setAction(null);
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  const remove = useApiMutation(
    (provenance: Provenance) => mutations.deleteCi(ciId, provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setAction(null);
        navigate("/ci");
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  if (isPending) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (isError || !ci) {
    return (
      <Panel>
        <EmptyState
          title={describeError(error, t)}
          action={<Button onClick={() => navigate("/ci")}>{t("ci.title")}</Button>}
        />
      </Panel>
    );
  }

  const relationCount = Object.entries(related ?? {})
    .filter(([key]) => key !== "documents")
    .reduce((acc, [, items]) => acc + items.length, 0);

  return (
    <>
      <div className="flex flex-col gap-3">
        <Link to="/ci" className="inline-flex items-center gap-1 text-xs text-muted hover:text-app">
          <ChevronLeft size={13} />
          {t("ci.title")}
        </Link>

        <header className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold tracking-tight">{ci.name}</h1>
              {ci.code && <span className="font-mono text-xs text-muted">{ci.code}</span>}
              <Badge tone={toneFor("ciStatus", ci.status)}>{te("ciStatus", ci.status)}</Badge>
              <Badge tone={toneFor("criticality", ci.criticality)}>
                {te("criticality", ci.criticality)}
              </Badge>
              {ci.archived_at && <Badge tone="warn">{t("ci.archived")}</Badge>}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              {te("ciType", ci.ci_type)}
              {ci.location && ` · ${ci.location.path}`}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {ci.archived_at ? (
              <Button icon={<ArchiveRestore size={14} />} onClick={() => setAction("restore")}>
                {t("app.restore")}
              </Button>
            ) : (
              <Button icon={<Archive size={14} />} onClick={() => setAction("archive")}>
                {t("app.archive")}
              </Button>
            )}
            <Button
              variant="ghost"
              icon={<Trash2 size={14} />}
              onClick={() => setAction("delete")}
              title={t("ci.deleteProtected")}
            >
              {t("app.delete")}
            </Button>
          </div>
        </header>

        <Tabs
          active={tab}
          onChange={(id) => setTab(id as Tab)}
          items={[
            { id: "overview", label: t("ci.overview") },
            { id: "related", label: t("ci.related"), badge: relationCount },
            { id: "documents", label: t("ci.documents"), badge: documents?.length ?? 0 },
            { id: "history", label: t("ci.history") },
          ]}
        />
      </div>

      {tab === "overview" && <CiOverviewTab ci={ci} />}
      {tab === "related" && <CiRelationsTab ciId={ci.id} />}
      {tab === "history" && <CiHistoryTab ciId={ci.id} />}
      {tab === "documents" && (
        <Panel title={t("ci.documents")} bodyClassName={documents?.length ? "p-0" : undefined}>
          {!documents?.length ? (
            <EmptyState title={t("ci.noDocuments")} />
          ) : (
            <ul className="divide-y divide-[rgb(var(--border))]/60">
              {documents.map((doc) => (
                <li key={doc.id} className="flex items-center gap-3 px-3 py-1.5">
                  <Link
                    to={`/documents/${doc.id}`}
                    className="min-w-0 flex-1 truncate text-sm text-accent hover:underline"
                  >
                    {doc.title}
                  </Link>
                  <span className="text-xs text-muted">{te("documentKind", doc.kind)}</span>
                  <Badge tone={toneFor("documentStatus", doc.status)}>
                    {te("documentStatus", doc.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      <ConfirmDialog
        open={action === "archive"}
        title={t("ci.archiveConfirm")}
        confirmLabel={t("app.archive")}
        pending={archive.isPending}
        onCancel={() => setAction(null)}
        onConfirm={(provenance) => archive.mutate(provenance)}
      />
      <ConfirmDialog
        open={action === "restore"}
        title={t("app.restore")}
        confirmLabel={t("app.restore")}
        pending={restore.isPending}
        onCancel={() => setAction(null)}
        onConfirm={(provenance) => restore.mutate(provenance)}
      />
      <ConfirmDialog
        open={action === "delete"}
        danger
        title={t("ci.deleteConfirm")}
        description={t("ci.deleteProtected")}
        confirmLabel={t("app.delete")}
        pending={remove.isPending}
        onCancel={() => setAction(null)}
        onConfirm={(provenance) => remove.mutate(provenance)}
      />
    </>
  );
}
