import { Trash2 } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  usePlatform,
  useProjects,
  useVirtualization,
  useVlans,
} from "@/shared/api/queries";
import { Button, IconButton } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const KINDS = ["CLUSTER", "MCP", "AGENT", "VM", "URL"] as const;

export function RoutesPage() {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const [open, setOpen] = useState(false);
  const remove = useApiMutation((id: string) => mutations.deleteRoute(id), [keys.platform], {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err) => toast.error(describeError(err, t)),
  });
  const rows = data?.routes ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("platform.routes")}
        subtitle={t("platform.routesHint")}
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            {t("platform.addRoute")}
          </Button>
        }
      />
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("platform.routeEmpty")}</p>
      ) : (
        <Panel>
          <ul className="flex flex-col gap-2">
            {rows.map((row) => (
              <li key={row.id} className="flex items-start justify-between gap-3 border-b border-app py-2 last:border-0">
                <div>
                  <p className="text-sm font-medium">{row.name}</p>
                  <p className="mt-1 font-mono text-xs">
                    {row.host}
                    {row.path}
                    <span className="text-muted"> → </span>
                    {row.target_name ?? t("platform.targetMissing")}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {te("routeTarget", row.target_kind)}
                    {row.vlan_label ? ` · VLAN ${row.vlan_label}` : ""}
                    {row.project_name ? ` · ${row.project_name}` : ""}
                  </p>
                </div>
                <IconButton label={t("app.delete")} onClick={() => remove.mutate(row.id)}>
                  <Trash2 size={13} />
                </IconButton>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <RouteDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function RouteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const { data } = usePlatform();
  const { data: projects } = useProjects();
  const { data: vlans } = useVlans({});
  const { data: virt } = useVirtualization();
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [path, setPath] = useState("/");
  const [kind, setKind] = useState("CLUSTER");
  const [targetId, setTargetId] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [vlanId, setVlanId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const targets =
    kind === "CLUSTER"
      ? (data?.clusters ?? []).map((item) => ({ value: item.id, label: item.name }))
      : kind === "MCP"
        ? (data?.mcp ?? []).map((item) => ({ value: item.id, label: item.name }))
        : kind === "AGENT"
          ? (data?.agents ?? []).map((item) => ({ value: item.id, label: item.name }))
          : kind === "VM"
            ? (virt?.vms ?? []).map((item) => ({ value: item.id, label: item.name }))
            : [];
  const save = useApiMutation((body: Record<string, unknown>) => mutations.createRoute(body), [keys.platform], {
    onSuccess: () => {
      toast.success(t("app.created"));
      setName("");
      setHost("");
      setPath("/");
      setTargetUrl("");
      setError(null);
      onClose();
    },
    onError: (err) => setError(describeError(err, t)),
  });
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("platform.addRoute")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || !host.trim() || save.isPending}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                host: host.trim(),
                path: path.trim() || "/",
                target_kind: kind,
                target_id: kind === "URL" ? null : targetId || null,
                target_url: kind === "URL" ? targetUrl.trim() : null,
                vlan_id: vlanId || null,
                project_id: projectId || null,
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
          <Field label={t("platform.hostName")} required>
            <Input value={host} placeholder="app.example.ru" onChange={(event) => setHost(event.target.value)} />
          </Field>
          <Field label={t("platform.path")}>
            <Input value={path} onChange={(event) => setPath(event.target.value)} />
          </Field>
        </div>
        <Field label={t("platform.target")}>
          <Select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setTargetId("");
            }}
            options={KINDS.map((value) => ({ value, label: te("routeTarget", value) }))}
          />
        </Field>
        {kind === "URL" ? (
          <Field label={t("platform.endpoint")} required>
            <Input value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} />
          </Field>
        ) : (
          <Field label={t("platform.target")} required>
            <Select
              value={targetId}
              placeholder="—"
              onChange={(event) => setTargetId(event.target.value)}
              options={targets}
            />
          </Field>
        )}
        <Field label="VLAN">
          <Select
            value={vlanId}
            placeholder="—"
            onChange={(event) => setVlanId(event.target.value)}
            options={(vlans ?? []).map((item) => ({
              value: item.id,
              label: `${item.vid} ${item.name}`,
            }))}
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
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
