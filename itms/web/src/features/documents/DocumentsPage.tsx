import { Plus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useDocuments,
  useMeta,
  type DocumentListParams,
} from "@/shared/api/queries";
import type { DocumentSummary } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { formatDate, formatRelative } from "@/shared/lib/format";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const PAGE_SIZE = 50;

function DocumentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data: meta } = useMeta();

  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("INSTRUCTION");
  const [summary, setSummary] = useState("");
  const [content, setContent] = useState("");

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createDocument(body),
    [["documents"], keys.dashboard],
    {
      onSuccess: (doc) => {
        toast.success(t("app.created"), doc.title);
        setTitle("");
        setSummary("");
        setContent("");
        onClose();
        navigate(`/documents/${doc.id}`);
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("documents.create")}
      width="md"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!title.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                title: title.trim(),
                kind,
                summary: summary.trim() || null,
                content,
                content_format: "markdown",
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("documents.name")} required>
          <Input value={title} autoFocus onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field label={t("documents.kind")}>
          <Select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            options={(meta?.document_kinds ?? []).map((value) => ({
              value,
              label: te("documentKind", value),
            }))}
          />
        </Field>
        <Field label={t("documents.summary")}>
          <Input value={summary} onChange={(event) => setSummary(event.target.value)} />
        </Field>
        <Field label={t("documents.content")} hint={t("documents.markdownHint")}>
          <Textarea
            rows={10}
            value={content}
            className="font-mono text-xs"
            onChange={(event) => setContent(event.target.value)}
          />
        </Field>
      </div>
    </Dialog>
  );
}

export function DocumentsPage() {
  const { t, te, locale } = useI18n();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);
  const { data: meta } = useMeta();

  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const reviewDue = params.get("review_due") === "1";
  const offset = Number(params.get("offset") ?? 0);
  const debouncedQ = useDebounced(q, 300);

  const patch = (next: Record<string, string | null>) => {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (!value) updated.delete(key);
      else updated.set(key, value);
    }
    if (!("offset" in next)) updated.delete("offset");
    setParams(updated, { replace: true });
  };

  const query: DocumentListParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      status: status ? [status] : undefined,
      review_due: reviewDue || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [debouncedQ, status, reviewDue, offset],
  );

  const { data, isFetching } = useDocuments(query);

  const columns: Array<Column<DocumentSummary>> = [
    {
      key: "title",
      header: t("documents.name"),
      render: (row) => <span className="font-medium">{row.title}</span>,
    },
    {
      key: "kind",
      header: t("documents.kind"),
      width: "11rem",
      render: (row) => <span className="text-muted">{te("documentKind", row.kind)}</span>,
    },
    {
      key: "status",
      header: t("documents.status"),
      width: "10rem",
      render: (row) => (
        <Badge tone={toneFor("documentStatus", row.status)}>
          {te("documentStatus", row.status)}
        </Badge>
      ),
    },
    {
      key: "version",
      header: t("documents.version"),
      width: "5rem",
      align: "right",
      render: (row) => row.current_version,
    },
    {
      key: "review_due_on",
      header: t("documents.reviewDue"),
      width: "9rem",
      render: (row) => {
        if (!row.review_due_on) return <span className="text-muted">—</span>;
        const overdue = new Date(row.review_due_on) < new Date();
        return (
          <span className={overdue ? "text-[rgb(var(--warn))]" : "text-muted"}>
            {formatDate(row.review_due_on, locale)}
          </span>
        );
      },
    },
    {
      key: "updated_at",
      header: t("ci.updated"),
      width: "9rem",
      align: "right",
      render: (row) => (
        <span className="text-xs text-muted">{formatRelative(row.updated_at, locale)}</span>
      ),
    },
  ];

  const hasFilters = Boolean(q || status || reviewDue);

  return (
    <>
      <PageHeader
        title={t("documents.title")}
        subtitle={t("documents.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
            {t("documents.create")}
          </Button>
        }
      />

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-app p-2.5">
          <Input
            value={q}
            placeholder={t("app.search")}
            onChange={(event) => patch({ q: event.target.value })}
            className="w-64"
          />
          <Select
            value={status}
            placeholder={`${t("documents.status")}: ${t("app.all")}`}
            onChange={(event) => patch({ status: event.target.value })}
            className="w-44"
            options={(meta?.document_statuses ?? []).map((value) => ({
              value,
              label: te("documentStatus", value),
            }))}
          />
          <Checkbox
            label={t("documents.reviewDueOnly")}
            checked={reviewDue}
            onChange={(event) => patch({ review_due: event.target.checked ? "1" : null })}
          />
          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              icon={<X size={13} />}
              onClick={() => setParams(new URLSearchParams(), { replace: true })}
            >
              {t("app.reset")}
            </Button>
          )}
          <span className="ml-auto text-xs tabular-nums text-muted">
            {t("app.total")}: {data?.total ?? 0}
          </span>
        </div>

        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(row) => row.id}
          loading={isFetching}
          emptyTitle={t("app.empty")}
          emptyHint={t("documents.emptyHint")}
          onRowClick={(row) => navigate(`/documents/${row.id}`)}
        />

        <Pagination
          total={data?.total ?? 0}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={(value) => patch({ offset: String(value) })}
          labels={{
            previous: t("app.previous"),
            next: t("app.next"),
            range: (from, to, total) => t("app.range", { from, to, total }),
          }}
        />
      </Panel>

      <DocumentDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}
