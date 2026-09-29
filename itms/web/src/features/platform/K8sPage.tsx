import { Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, usePlatform, useProjects, useVirtualization } from "@/shared/api/queries";
import { Button, IconButton } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const ENVS = ["PROD", "STAGE", "DEV", "OTHER"] as const;

export function K8sPage() {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const [open, setOpen] = useState(false);
  const remove = useApiMutation((id: string) => mutations.deleteCluster(id), [keys.platform], {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err) => toast.error(describeError(err, t)),
  });
  const rows = data?.clusters ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("platform.k8s")}
        subtitle={t("platform.k8sHint")}
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            {t("platform.addCluster")}
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
                    {te("platformEnv", row.environment)}
                    {row.version ? ` · ${row.version}` : ""}
                    {row.project_name ? ` · ${row.project_name}` : ""}
                  </p>
                  {row.endpoint && <p className="mt-2 font-mono text-xs">{row.endpoint}</p>}
                  {row.notes && <p className="mt-2 text-sm">{row.notes}</p>}
                </div>
                <IconButton label={t("app.delete")} onClick={() => remove.mutate(row.id)}>
                  <Trash2 size={13} />
                </IconButton>
              </div>
            </Panel>
          ))}
        </div>
      )}
      <ClusterDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function ClusterDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const { data: projects } = useProjects();
  const { data: virt } = useVirtualization();
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [version, setVersion] = useState("");
  const [environment, setEnvironment] = useState("PROD");
  const [projectId, setProjectId] = useState("");
  const [hostId, setHostId] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation((body: Record<string, unknown>) => mutations.createCluster(body), [keys.platform], {
    onSuccess: () => {
      toast.success(t("app.created"));
      setName("");
      setEndpoint("");
      setVersion("");
      setNotes("");
      setError(null);
      onClose();
    },
    onError: (err) => setError(describeError(err, t)),
  });
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("platform.addCluster")}
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
                endpoint: endpoint.trim() || null,
                version: version.trim() || null,
                environment,
                project_id: projectId || null,
                host_id: hostId || null,
                notes: notes.trim() || null,
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
        <Field label={t("platform.endpoint")} hint={t("platform.endpointHint")}>
          <Input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("platform.version")}>
            <Input value={version} onChange={(event) => setVersion(event.target.value)} />
          </Field>
          <Field label={t("platform.environment")}>
            <Select
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
              options={ENVS.map((value) => ({ value, label: te("platformEnv", value) }))}
            />
          </Field>
        </div>
        <Field label={t("nav.projects")}>
          <Select
            value={projectId}
            placeholder="—"
            onChange={(event) => setProjectId(event.target.value)}
            options={(projects ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
        </Field>
        <Field label={t("platform.host")}>
          <Select
            value={hostId}
            placeholder="—"
            onChange={(event) => setHostId(event.target.value)}
            options={(virt?.hosts ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
        </Field>
        <Field label={t("office.notes")}>
          <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
