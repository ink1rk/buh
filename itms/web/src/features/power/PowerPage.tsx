import { Plus, Zap } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, usePower } from "@/shared/api/queries";
import type { PowerNodeRow, PowerOverview } from "@/shared/api/types";
import { Badge, type Tone } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

const NODE_TYPES = [
  "INPUT",
  "PANEL",
  "BREAKER",
  "LINE",
  "TRANSFER_SWITCH",
  "UPS",
  "PDU",
  "OUTLET",
  "PSU",
  "GENERIC_LOAD",
] as const;

const THREE_PHASE = new Set(["INPUT", "PANEL", "BREAKER", "LINE", "TRANSFER_SWITCH", "UPS", "PDU"]);

function formatKw(watts: number): string {
  return `${(watts / 1000).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} кВт`;
}

function headroomTone(watts: number | null): Tone {
  if (watts == null) return "neutral";
  if (watts < 0) return "danger";
  if (watts < 1000) return "warn";
  return "ok";
}

function failoverTone(verdict: string | null): Tone {
  if (verdict === "RESILIENT") return "ok";
  if (verdict === "AT_RISK" || verdict === "SINGLE_FEED" || verdict === "SAME_FEED") return "warn";
  return "neutral";
}

function Metric({
  label,
  watts,
  testId,
}: {
  label: string;
  watts: number;
  testId: string;
}) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="text-lg font-semibold tabular-nums" data-testid={testId} data-watts={watts}>
        {formatKw(watts)}
      </div>
    </div>
  );
}

function CreateNodeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [nodeType, setNodeType] = useState<string>("GENERIC_LOAD");
  const [phase, setPhase] = useState("L1");
  const [nameplate, setNameplate] = useState("");
  const [maxLoad, setMaxLoad] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createPowerNode(body),
    [keys.power],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  const three = THREE_PHASE.has(nodeType);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("power.createNode")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                name: name.trim(),
                code: code.trim() || null,
                node_type: nodeType,
                phases: three ? 3 : 1,
                phase_label: three ? "L1L2L3" : phase,
                power_nameplate_w: nameplate ? Number(nameplate) : null,
                max_load_w: maxLoad ? Number(maxLoad) : null,
                utilization: nameplate ? 0.8 : null,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("power.name")} required htmlFor="power-name">
          <Input id="power-name" value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("power.code")} htmlFor="power-code">
          <Input id="power-code" value={code} onChange={(event) => setCode(event.target.value)} />
        </Field>
        <Field label={t("power.nodeType")} htmlFor="power-type">
          <Select
            id="power-type"
            value={nodeType}
            onChange={(event) => setNodeType(event.target.value)}
            options={NODE_TYPES.map((item) => ({ value: item, label: te("powerNodeType", item) }))}
          />
        </Field>
        {!three && (
          <Field label={t("power.phase")} htmlFor="power-phase">
            <Select
              id="power-phase"
              value={phase}
              onChange={(event) => setPhase(event.target.value)}
              options={[
                { value: "L1", label: "L1" },
                { value: "L2", label: "L2" },
                { value: "L3", label: "L3" },
              ]}
            />
          </Field>
        )}
        <Field label={t("power.nameplate")} htmlFor="power-nameplate">
          <Input
            id="power-nameplate"
            type="number"
            value={nameplate}
            onChange={(event) => setNameplate(event.target.value)}
          />
        </Field>
        <Field label={t("power.maxLoad")} htmlFor="power-max">
          <Input id="power-max" type="number" value={maxLoad} onChange={(event) => setMaxLoad(event.target.value)} />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function CreateLinkDialog({
  open,
  onClose,
  nodes,
}: {
  open: boolean;
  onClose: () => void;
  nodes: PowerNodeRow[];
}) {
  const { t } = useI18n();
  const [source, setSource] = useState(nodes[0]?.id ?? "");
  const [target, setTarget] = useState(nodes[1]?.id ?? nodes[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createPowerLink(body),
    [keys.power],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("power.createLink")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!source || !target || source === target || create.isPending}
            onClick={() => create.mutate({ source_node_id: source, target_node_id: target })}
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("power.feeder")} htmlFor="power-source">
          <Select
            id="power-source"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            options={nodes.map((node) => ({ value: node.id, label: node.name }))}
          />
        </Field>
        <Field label={t("power.consumer")} htmlFor="power-target">
          <Select
            id="power-target"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            options={nodes.map((node) => ({ value: node.id, label: node.name }))}
          />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function ForecastBlock({ overview }: { overview: PowerOverview }) {
  const { t } = useI18n();
  const scenario = overview.scenarios[0];
  const forecast = scenario?.forecast;
  if (!scenario || !forecast) return null;
  const deficit = forecast.deficit_w ?? 0;
  return (
    <Panel title={scenario.name} className="mb-4">
      <p className="mb-3 text-sm text-muted">
        {scenario.project_key ? `${scenario.project_key}. ` : ""}
        {scenario.description}
      </p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3" data-testid="power-forecast">
        <Metric label={t("power.current")} watts={forecast.current_estimated_w} testId="forecast-current" />
        <Metric label={t("power.added")} watts={forecast.added_estimated_w} testId="forecast-added" />
        <Metric label={t("power.target")} watts={forecast.target_estimated_w} testId="forecast-target" />
        <Metric label={t("power.deficit")} watts={deficit} testId="forecast-deficit" />
        <Metric label={t("power.required")} watts={forecast.required_input_w} testId="forecast-required" />
        <Metric label={t("power.breaker50")} watts={forecast.recommended_3x50_w} testId="forecast-breaker" />
      </div>
      <p className="mt-3 text-sm">
        {deficit > 0 ? t("power.deficitText") : t("power.reserveText")}
        {forecast.ups_loss_w
          ? ` ${t("power.upsLoss", { watts: forecast.ups_loss_w })}`
          : ""}
      </p>
    </Panel>
  );
}

export function PowerPage() {
  const { t, te } = useI18n();
  const power = usePower();
  const [nodeOpen, setNodeOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const overview = power.data;
  const primary = overview?.nodes.find((node) => node.id === overview.primary_input_id) ?? null;
  const trace = primary?.trace ?? [];

  return (
    <div data-testid="power-page">
      <PageHeader
        title={t("power.title")}
        subtitle={t("power.subtitle")}
        actions={
          <>
            <Button onClick={() => setLinkOpen(true)} disabled={!overview?.nodes.length}>
              {t("power.createLink")}
            </Button>
            <Button variant="primary" data-testid="create-power-node" onClick={() => setNodeOpen(true)}>
              <Plus size={16} />
              {t("power.createNode")}
            </Button>
          </>
        }
      />
      {primary && (
        <Panel title={primary.name} className="mb-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label={t("power.estimated")} watts={primary.inlet_w} testId="input-estimated" />
            <Metric label={t("power.nameplate")} watts={primary.nameplate_w} testId="input-nameplate" />
            <div>
              <div className="text-xs text-muted">{t("power.headroom")}</div>
              <div
                className="text-lg font-semibold tabular-nums"
                data-testid="input-headroom"
                data-watts={primary.headroom_w ?? 0}
              >
                <Badge tone={headroomTone(primary.headroom_w)}>
                  {primary.headroom_w == null ? "—" : formatKw(primary.headroom_w)}
                </Badge>
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">{t("power.limit")}</div>
              <div className="text-lg font-semibold tabular-nums">
                {primary.limit_w == null ? "—" : formatKw(primary.limit_w)}
              </div>
            </div>
          </div>
        </Panel>
      )}
      {overview && <ForecastBlock overview={overview} />}
      <Panel
        title={t("power.nodes")}
        actions={
          <span className="inline-flex items-center gap-1 text-xs text-muted">
            <Zap size={14} />
            {overview?.feeds.map((feed) => feed.name).join(" · ")}
          </span>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-2 py-1">{t("power.name")}</th>
                <th className="px-2 py-1">{t("power.nodeType")}</th>
                <th className="px-2 py-1">{t("power.estimated")}</th>
                <th className="px-2 py-1">{t("power.headroom")}</th>
                <th className="px-2 py-1">{t("power.failover")}</th>
                <th className="px-2 py-1">{t("power.warnings")}</th>
              </tr>
            </thead>
            <tbody>
              {overview?.nodes.map((node) => (
                <tr key={node.id} data-testid="power-node" data-code={node.code ?? ""}>
                  <td className="px-2 py-1.5">
                    <div className="font-medium">{node.name}</div>
                    <div className="text-xs text-muted">{node.code}</div>
                  </td>
                  <td className="px-2 py-1.5">{te("powerNodeType", node.node_type)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{formatKw(node.inlet_w)}</td>
                  <td className="px-2 py-1.5">
                    {node.headroom_w == null ? (
                      "—"
                    ) : (
                      <Badge tone={headroomTone(node.headroom_w)}>{formatKw(node.headroom_w)}</Badge>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    {node.failover ? (
                      <Badge tone={failoverTone(node.failover)} title={node.failover_detail ?? undefined}>
                        {te("failover", node.failover)}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-xs">
                    {node.warnings.map((warning) => warning.message).join(" ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {primary && trace.length > 0 && (
          <details className="mt-3" data-testid="power-trace" open>
            <summary className="cursor-pointer text-sm font-medium">{t("power.trace")}</summary>
            <ol className="mt-2 flex flex-col gap-1 text-xs text-muted">
              {trace.map((step, index) => (
                <li key={`${String(step.source)}-${index}`}>
                  {String(step.source)}
                  {step.formula ? ` — ${String(step.formula)}` : ""}
                  {step.value_w != null ? ` — ${String(step.value_w)} Вт` : ""}
                </li>
              ))}
            </ol>
          </details>
        )}
      </Panel>
      <CreateNodeDialog open={nodeOpen} onClose={() => setNodeOpen(false)} />
      {linkOpen && overview && (
        <CreateLinkDialog open={linkOpen} onClose={() => setLinkOpen(false)} nodes={overview.nodes} />
      )}
    </div>
  );
}
