import { Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, usePlatform, useProjects } from "@/shared/api/queries";
import { Button, IconButton } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

export function AgentsPage() {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const [open, setOpen] = useState(false);
  const remove = useApiMutation((id: string) => mutations.deleteAgent(id), [keys.platform], {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err) => toast.error(describeError(err, t)),
  });
  const rows = data?.agents ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("platform.agents")}
        subtitle={t("platform.agentsHint")}
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            {t("platform.addAgent")}
          </Button>
        }
      />
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("app.empty")}</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {rows.map((row) => (
            <Panel key={row.id}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-medium">{row.name}</h2>
                  <p className="mt-1 text-xs text-muted">
                    {te("agentKind", row.kind)}
                    {row.model ? ` · ${row.model}` : ""}
                    {row.project_name ? ` · ${row.project_name}` : ""}
                  </p>
                  {row.endpoint && <p className="mt-2 font-mono text-xs">{row.endpoint}</p>}
                  {row.mcp_names.length > 0 && (
                    <p className="mt-2 text-xs">MCP: {row.mcp_names.join(", ")}</p>
                  )}
                  {row.description && <p className="mt-2 text-sm">{row.description}</p>}
                </div>
                <IconButton label={t("app.delete")} onClick={() => remove.mutate(row.id)}>
                  <Trash2 size={13} />
                </IconButton>
              </div>
            </Panel>
          ))}
        </div>
      )}
      <AgentDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function AgentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const { data: projects } = useProjects();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("OPENCODE");
  const [endpoint, setEndpoint] = useState("");
  const [model, setModel] = useState("");
  const [projectId, setProjectId] = useState("");
  const [mcpId, setMcpId] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation((body: Record<string, unknown>) => mutations.createAgent(body), [keys.platform], {
    onSuccess: () => {
      toast.success(t("app.created"));
      setName("");
      setEndpoint("");
      setModel("");
      setDescription("");
      setError(null);
      onClose();
    },
    onError: (err) => setError(describeError(err, t)),
  });
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("platform.addAgent")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || save.isPending}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                kind,
                endpoint: endpoint.trim() || null,
                model: model.trim() || null,
                project_id: projectId || null,
                description: description.trim() || null,
                mcp_ids: mcpId ? [mcpId] : [],
              })
            }
          >
            {t("app.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("platform.name")} required>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("platform.kind")}>
            <Select
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              options={[
                { value: "OPENCODE", label: te("agentKind", "OPENCODE") },
                { value: "OTHER", label: te("agentKind", "OTHER") },
              ]}
            />
          </Field>
          <Field label={t("platform.model")}>
            <Input value={model} onChange={(event) => setModel(event.target.value)} />
          </Field>
        </div>
        <Field label={t("platform.endpoint")}>
          <Input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
        </Field>
        <Field label={t("platform.mcp")}>
          <Select
            value={mcpId}
            placeholder="—"
            onChange={(event) => setMcpId(event.target.value)}
            options={(data?.mcp ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
        </Field>
        <Field label={t("nav.projects")}>
          <Select
            value={projectId}
            placeholder="—"
            onChange={(event) => setProjectId(event.target.value)}
            options={(projects ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
        </Field>
        <Field label={t("platform.description")}>
          <Textarea value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
