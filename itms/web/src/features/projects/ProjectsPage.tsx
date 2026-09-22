import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useInbox, useProjects, useSavedViews } from "@/shared/api/queries";
import type { InboxItem, ProjectSummary } from "@/shared/api/types";
import { Badge, type Tone } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { FormError, PageHeader } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function healthTone(status: string): Tone {
  if (status === "DELAYED") return "danger";
  if (status === "AT_RISK") return "warn";
  if (status === "ON_TRACK") return "ok";
  return "neutral";
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useApiMutation(
    (body: Record<string, unknown>) =>
      body.template ? mutations.createFromTemplate(body) : mutations.createProject(body),
    [keys.projects],
    {
      onSuccess: (created) => {
        toast.success(t("app.created"));
        onClose();
        navigate(`/projects/${created.project.id}`);
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("projects.create")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!key.trim() || !name.trim() || create.isPending}
            onClick={() => {
              if (template) {
                create.mutate({ template, key: key.trim(), name: name.trim() });
                return;
              }
              create.mutate({
                key: key.trim(),
                name: name.trim(),
                description: description.trim(),
              });
            }}
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("projects.key")} required htmlFor="project-key">
          <Input id="project-key" value={key} autoFocus onChange={(event) => setKey(event.target.value)} />
        </Field>
        <Field label={t("projects.name")} required htmlFor="project-name">
          <Input id="project-name" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("projects.template")} htmlFor="project-template">
          <Select
            id="project-template"
            value={template}
            placeholder={t("projects.template")}
            options={[{ value: "infrastructure", label: t("projects.fromTemplate") }]}
            onChange={(event) => setTemplate(event.target.value)}
          />
        </Field>
        <Field label={t("projects.description")} htmlFor="project-description">
          <Textarea
            id="project-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function SavedViews({
  active,
  onPick,
}: {
  active: string;
  onPick: (bucket: string) => void;
}) {
  const { t } = useI18n();
  const { data } = useSavedViews();
  const [name, setName] = useState("");
  const [bucket, setBucket] = useState("overdue");
  const save = useApiMutation((body: Record<string, unknown>) => mutations.saveView(body), [keys.views], {
    onSuccess: () => {
      setName("");
      toast.success(t("app.saved"));
    },
    onError: (err) => toast.error(describeError(err, t)),
  });
  const buckets = [
    ["overdue", t("projects.overdue")],
    ["today", t("projects.today")],
    ["upcoming", t("projects.upcoming")],
    ["undated", t("projects.undated")],
  ] as const;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="saved-views">
      {(data ?? []).map((view) => (
        <button
          key={view.id}
          type="button"
          className={
            active === (view.bucket ?? "")
              ? "rounded-md bg-[rgb(var(--surface-muted))] px-2 py-1 text-xs"
              : "rounded-md px-2 py-1 text-xs text-muted"
          }
          onClick={() => onPick(view.bucket ?? "")}
        >
          {view.name}
        </button>
      ))}
      <Input
        className="w-44"
        value={name}
        placeholder={t("projects.viewName")}
        onChange={(event) => setName(event.target.value)}
      />
      <Select
        value={bucket}
        options={buckets.map(([value, label]) => ({ value, label }))}
        onChange={(event) => setBucket(event.target.value)}
      />
      <Button
        data-testid="save-view"
        disabled={!name.trim() || save.isPending}
        onClick={() => save.mutate({ name: name.trim(), bucket })}
      >
        {t("projects.saveView")}
      </Button>
    </div>
  );
}

function Inbox({ onOpen, only }: { onOpen: (projectId: string) => void; only: string }) {
  const { t } = useI18n();
  const { data } = useInbox();
  const buckets = [
    ["overdue", t("projects.overdue")],
    ["today", t("projects.today")],
    ["upcoming", t("projects.upcoming")],
    ["undated", t("projects.undated")],
  ] as const;
  const shown = only ? buckets.filter(([bucket]) => bucket === only) : buckets;
  return (
    <div className="mb-4 grid gap-3 md:grid-cols-4" data-testid="project-inbox">
      {shown.map(([bucket, label]) => {
        const rows = (data ?? []).filter((item: InboxItem) => item.bucket === bucket);
        return (
          <section key={bucket} className="surface rounded-lg p-3" data-testid={`inbox-${bucket}`}>
            <h2 className="mb-2 text-xs font-medium text-muted">
              {label} · {rows.length}
            </h2>
            <ul className="flex flex-col gap-1">
              {rows.slice(0, 6).map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="w-full truncate text-left text-sm"
                    onClick={() => onOpen(item.project_id)}
                  >
                    <span className="mr-2 font-mono text-xs text-muted">{item.label}</span>
                    {item.title}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export function ProjectsPage() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useProjects();
  const [creating, setCreating] = useState(false);
  const [only, setOnly] = useState("");

  const columns: Array<Column<ProjectSummary>> = [
    {
      key: "key",
      header: t("projects.key"),
      width: "90px",
      render: (row) => <span className="font-mono text-xs">{row.key}</span>,
    },
    {
      key: "name",
      header: t("projects.name"),
      render: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "status",
      header: t("projects.status"),
      render: (row) => te("projectStatus", row.status),
    },
    {
      key: "health",
      header: t("projects.health"),
      render: (row) => <Badge tone={healthTone(row.health)}>{te("health", row.health)}</Badge>,
    },
    {
      key: "progress",
      header: t("projects.progress"),
      width: "90px",
      render: (row) => <span className="tabular-nums">{row.progress_pct}%</span>,
    },
    {
      key: "open",
      header: t("projects.openTasks"),
      width: "90px",
      render: (row) => (
        <span className="tabular-nums text-muted">
          {row.open_task_count}/{row.task_count}
        </span>
      ),
    },
    {
      key: "due",
      header: t("projects.due"),
      render: (row) => <span className="text-muted">{row.due_date ?? "—"}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title={t("projects.title")}
        subtitle={t("projects.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>
            {t("projects.create")}
          </Button>
        }
      />
      <SavedViews active={only} onPick={setOnly} />
      <Inbox only={only} onOpen={(projectId) => navigate(`/projects/${projectId}`)} />
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(row) => row.id}
        loading={isLoading}
        emptyTitle={t("projects.empty")}
        emptyHint={t("projects.emptyHint")}
        onRowClick={(row) => navigate(`/projects/${row.id}`)}
      />
      <CreateProjectDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
