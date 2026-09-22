import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useProjects } from "@/shared/api/queries";
import type { ProjectSummary } from "@/shared/api/types";
import { Badge, type Tone } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Textarea } from "@/shared/ui/Field";
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
  const [error, setError] = useState<string | null>(null);

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createProject(body),
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
            onClick={() =>
              create.mutate({
                key: key.trim(),
                name: name.trim(),
                description: description.trim(),
              })
            }
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

export function ProjectsPage() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useProjects();
  const [creating, setCreating] = useState(false);

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
