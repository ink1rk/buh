import { Archive, ChevronLeft, Link2, Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useCiList,
  useDocument,
  useDocumentVersions,
  useMeta,
} from "@/shared/api/queries";
import { useDebounced } from "@/shared/hooks";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { EmptyState, KeyValue, Panel, Spinner } from "@/shared/ui/Layout";
import { Markdown } from "@/shared/ui/Markdown";
import { Tabs } from "@/shared/ui/Tabs";
import { toast } from "@/shared/ui/toast";

import { ConfirmDialog } from "../provenance/ReasonField";

type Tab = "content" | "versions" | "links";

function LinkDialog({
  open,
  documentId,
  onClose,
}: {
  open: boolean;
  documentId: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const [ciId, setCiId] = useState("");
  const debounced = useDebounced(search, 250);
  const { data: candidates } = useCiList({ q: debounced || undefined, limit: 25, offset: 0 });

  const link = useApiMutation(
    (body: Record<string, unknown>) => mutations.linkDocument(documentId, body),
    [keys.document(documentId)],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setCiId("");
        onClose();
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("documents.linkCi")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!ciId || link.isPending}
            onClick={() => link.mutate({ entity_type: "CI", entity_id: ciId, relation: null })}
          >
            {t("app.apply")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("app.search")}>
          <Input
            value={search}
            autoFocus
            placeholder={t("ci.searchTarget")}
            onChange={(event) => setSearch(event.target.value)}
          />
        </Field>
        <Field label={t("ci.title")} required>
          <Select
            value={ciId}
            size={8}
            className="h-40"
            placeholder={t("app.nothingSelected")}
            onChange={(event) => setCiId(event.target.value)}
            options={(candidates?.items ?? []).map((item) => ({
              value: item.id,
              label: item.code ? `${item.code} — ${item.name}` : item.name,
            }))}
          />
        </Field>
      </div>
    </Dialog>
  );
}

export function DocumentDetailPage() {
  const { t, te, locale } = useI18n();
  const { documentId = "" } = useParams();
  const { data: meta } = useMeta();

  const [tab, setTab] = useState<Tab>("content");
  const [editing, setEditing] = useState(false);
  const [draftContent, setDraftContent] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [linkOpen, setLinkOpen] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);

  const { data: doc, isPending } = useDocument(documentId);
  const { data: versions } = useDocumentVersions(documentId);

  const invalidate = [keys.document(documentId), keys.documentVersions(documentId), ["documents"]];

  const update = useApiMutation(
    (body: Record<string, unknown>) => mutations.updateDocument(documentId, body),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setEditing(false);
        setChangeNote("");
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const restore = useApiMutation(
    (version: number) => mutations.restoreDocumentVersion(documentId, version),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setRestoringVersion(null);
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const archive = useApiMutation(
    (provenance: Provenance) => mutations.archiveDocument(documentId, provenance),
    invalidate,
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setArchiving(false);
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const unlink = useApiMutation((linkId: string) => mutations.unlinkDocument(linkId), invalidate, {
    onError: (error) => toast.error(describeError(error, t)),
  });

  if (isPending || !doc) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const startEdit = () => {
    setDraftContent(doc.content ?? "");
    setEditing(true);
    setTab("content");
  };

  return (
    <>
      <div className="flex flex-col gap-3">
        <Link
          to="/documents"
          className="inline-flex items-center gap-1 text-xs text-muted hover:text-app"
        >
          <ChevronLeft size={13} />
          {t("documents.title")}
        </Link>

        <header className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold tracking-tight">{doc.title}</h1>
              <Badge tone={toneFor("documentStatus", doc.status)}>
                {te("documentStatus", doc.status)}
              </Badge>
              <Badge>v{doc.current_version}</Badge>
            </div>
            <p className="mt-0.5 text-xs text-muted">
              {te("documentKind", doc.kind)}
              {doc.summary && ` · ${doc.summary}`}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button icon={<Link2 size={14} />} onClick={() => setLinkOpen(true)}>
              {t("documents.linkCi")}
            </Button>
            {!editing && (
              <Button icon={<Pencil size={14} />} onClick={startEdit}>
                {t("app.edit")}
              </Button>
            )}
            <Button icon={<Archive size={14} />} onClick={() => setArchiving(true)}>
              {t("app.archive")}
            </Button>
          </div>
        </header>

        <Tabs
          active={tab}
          onChange={(id) => setTab(id as Tab)}
          items={[
            { id: "content", label: t("documents.content") },
            { id: "versions", label: t("documents.versions"), badge: versions?.length ?? 0 },
            { id: "links", label: t("documents.links"), badge: doc.links.length },
          ]}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_18rem]">
        <div className="flex flex-col gap-4">
          {tab === "content" &&
            (editing ? (
              <Panel
                title={t("documents.saveNewVersion")}
                actions={
                  <>
                    <Button size="sm" icon={<X size={13} />} onClick={() => setEditing(false)}>
                      {t("app.cancel")}
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={update.isPending}
                      onClick={() =>
                        update.mutate({
                          content: draftContent,
                          content_format: "markdown",
                          change_note: changeNote.trim() || null,
                        })
                      }
                    >
                      {t("app.save")}
                    </Button>
                  </>
                }
              >
                <div className="flex flex-col gap-3">
                  <Field label={t("documents.content")} hint={t("documents.markdownHint")}>
                    <Textarea
                      rows={22}
                      value={draftContent}
                      className="font-mono text-xs"
                      onChange={(event) => setDraftContent(event.target.value)}
                    />
                  </Field>
                  <Field label={t("documents.changeNote")}>
                    <Input
                      value={changeNote}
                      onChange={(event) => setChangeNote(event.target.value)}
                    />
                  </Field>
                </div>
              </Panel>
            ) : (
              <Panel title={t("documents.content")}>
                {doc.content?.trim() ? (
                  <Markdown source={doc.content} />
                ) : (
                  <EmptyState title={t("app.empty")} />
                )}
              </Panel>
            ))}

          {tab === "versions" && (
            <Panel title={t("documents.versions")} bodyClassName="p-0">
              {!versions?.length ? (
                <EmptyState title={t("documents.noVersions")} />
              ) : (
                <ul className="divide-y divide-[rgb(var(--border))]/60">
                  {versions.map((version) => (
                    <li key={version.id} className="flex items-center gap-3 px-3 py-1.5">
                      <Badge tone={version.is_current ? "accent" : "neutral"}>
                        v{version.version}
                      </Badge>
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {version.change_note ?? version.title}
                      </span>
                      <span className="shrink-0 text-xs text-muted">
                        {formatDateTime(version.created_at, locale)}
                      </span>
                      {!version.is_current && (
                        <IconButton
                          label={t("documents.restoreVersion")}
                          onClick={() => setRestoringVersion(version.version)}
                        >
                          <RotateCcw size={13} />
                        </IconButton>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}

          {tab === "links" && (
            <Panel title={t("documents.links")} bodyClassName="p-0">
              {!doc.links.length ? (
                <EmptyState title={t("documents.noLinks")} />
              ) : (
                <ul className="divide-y divide-[rgb(var(--border))]/60">
                  {doc.links.map((link) => (
                    <li key={link.id} className="group flex items-center gap-3 px-3 py-1.5">
                      <span className="w-28 shrink-0 text-xs text-muted">
                        {te("entityType", link.entity_type)}
                      </span>
                      {link.entity_type === "CI" ? (
                        <Link
                          to={`/ci/${link.entity_id}`}
                          className="min-w-0 flex-1 truncate text-sm text-accent hover:underline"
                        >
                          {link.entity_id}
                        </Link>
                      ) : (
                        <span className="min-w-0 flex-1 truncate text-sm">{link.entity_id}</span>
                      )}
                      <IconButton
                        label={t("documents.unlink")}
                        className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                        onClick={() => unlink.mutate(link.id)}
                      >
                        <Trash2 size={13} />
                      </IconButton>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
        </div>

        <Panel title={t("documents.status")}>
          <div className="flex flex-col gap-3">
            <Field label={t("documents.status")}>
              <Select
                value={doc.status}
                onChange={(event) => update.mutate({ status: event.target.value })}
                options={(meta?.document_statuses ?? []).map((value) => ({
                  value,
                  label: te("documentStatus", value),
                }))}
              />
            </Field>
            <KeyValue
              items={[
                { label: t("documents.currentVersion"), value: doc.current_version },
                { label: t("documents.reviewDue"), value: formatDate(doc.review_due_on, locale) },
                { label: t("ci.updated"), value: formatDateTime(doc.updated_at, locale) },
                { label: t("ci.created_at"), value: formatDateTime(doc.created_at, locale) },
              ]}
            />
          </div>
        </Panel>
      </div>

      <LinkDialog open={linkOpen} documentId={documentId} onClose={() => setLinkOpen(false)} />

      <ConfirmDialog
        open={archiving}
        title={t("documents.archiveConfirm")}
        confirmLabel={t("app.archive")}
        pending={archive.isPending}
        onCancel={() => setArchiving(false)}
        onConfirm={(provenance) => archive.mutate(provenance)}
      />

      <Dialog
        open={restoringVersion !== null}
        onClose={() => setRestoringVersion(null)}
        title={t("documents.restoreVersionConfirm", { version: restoringVersion ?? 0 })}
        width="sm"
        footer={
          <>
            <Button onClick={() => setRestoringVersion(null)}>{t("app.cancel")}</Button>
            <Button
              variant="primary"
              disabled={restore.isPending}
              onClick={() => restoringVersion !== null && restore.mutate(restoringVersion)}
            >
              {t("app.confirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">{t("documents.restoreVersionHint")}</p>
      </Dialog>
    </>
  );
}
