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

const TRANSPORTS = ["HTTP", "SSE", "STDIO"] as const;

export function McpPage() {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const [open, setOpen] = useState(false);
  const remove = useApiMutation((id: string) => mutations.deleteMcp(id), [keys.platform], {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err) => toast.error(describeError(err, t)),
  });
  const rows = data?.mcp ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("platform.mcp")}
        subtitle={t("platform.mcpHint")}
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            {t("platform.addMcp")}
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
                <div className="min-w-0">
                  <h2 className="text-sm font-medium">{row.name}</h2>
                  <p className="mt-1 truncate font-mono text-xs">{row.endpoint}</p>
                  <p className="mt-1 text-xs text-muted">
                    {te("mcpTransport", row.transport)}
                    {row.cluster_name ? ` · ${row.cluster_name}` : ""}
                    {row.project_name ? ` · ${row.project_name}` : ""}
                  </p>
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
      <McpDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function McpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const { data: projects } = useProjects();
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [transport, setTransport] = useState("HTTP");
  const [clusterId, setClusterId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation((body: Record<string, unknown>) => mutations.createMcp(body), [keys.platform], {
    onSuccess: () => {
      toast.success(t("app.created"));
      setName("");
      setEndpoint("");
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
      title={t("platform.addMcp")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || !endpoint.trim() || save.isPending}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                endpoint: endpoint.trim(),
                transport,
                cluster_id: clusterId || null,
                project_id: projectId || null,
                description: description.trim() || null,
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
        <Field label={t("platform.endpoint")} hint={t("platform.mcpEndpointHint")} required>
          <Input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
        </Field>
        <Field label={t("platform.transport")}>
          <Select
            value={transport}
            onChange={(event) => setTransport(event.target.value)}
            options={TRANSPORTS.map((value) => ({ value, label: te("mcpTransport", value) }))}
          />
        </Field>
        <Field label={t("platform.k8s")}>
          <Select
            value={clusterId}
            placeholder="—"
            onChange={(event) => setClusterId(event.target.value)}
            options={(data?.clusters ?? []).map((item) => ({ value: item.id, label: item.name }))}
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
