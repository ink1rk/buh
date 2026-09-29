import {
  BaseEdge,
  EdgeLabelRenderer,
  Handle,
  Position,
  getSmoothStepPath,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react";

import { useI18n } from "@/i18n";
import { cn } from "@/shared/lib/cn";
import { Badge, toneFor } from "@/shared/ui/Badge";

import type { FlowEdge, FlowNode } from "./diagramView";

const HANDLE = "!h-1.5 !w-1.5 !border-0 !bg-transparent !opacity-0";

function formatKw(watts: number): string {
  return `${(watts / 1000).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} кВт`;
}

function DeviceNode({ data, selected }: NodeProps<FlowNode>) {
  const { te } = useI18n();
  const role = data.powerNodeType
    ? te("powerNodeType", data.powerNodeType)
    : data.role
      ? te("deviceRole", data.role)
      : data.ciType
        ? te("ciType", data.ciType)
        : null;
  const border =
    data.criticality === "CRITICAL"
      ? "border-l-[rgb(var(--danger))]"
      : data.criticality === "HIGH"
        ? "border-l-[rgb(var(--warn))]"
        : "border-l-[rgb(var(--accent))]";

  return (
    <div
      className={cn(
        "w-[220px] rounded-md border border-l-4 border-app bg-surface px-2.5 py-2 shadow-sm",
        border,
        selected && "ring-2 ring-[rgb(var(--accent))]",
      )}
      data-testid="diagram-node"
      data-code={data.code ?? ""}
    >
      <Handle id="in-top" type="target" position={Position.Top} className={HANDLE} />
      <Handle id="out-top" type="source" position={Position.Top} className={HANDLE} />
      <Handle id="in-bottom" type="target" position={Position.Bottom} className={HANDLE} />
      <Handle id="out-bottom" type="source" position={Position.Bottom} className={HANDLE} />
      <Handle id="in-left" type="target" position={Position.Left} className={HANDLE} />
      <Handle id="out-left" type="source" position={Position.Left} className={HANDLE} />
      <Handle id="in-right" type="target" position={Position.Right} className={HANDLE} />
      <Handle id="out-right" type="source" position={Position.Right} className={HANDLE} />
      <div className="flex items-start justify-between gap-2">
        <p className="truncate text-sm font-semibold leading-tight">{data.label}</p>
        {data.status && (
          <Badge tone={toneFor("ciStatus", data.status)} className="shrink-0">
            {te("ciStatus", data.status)}
          </Badge>
        )}
      </div>
      <p className="mt-1 truncate font-mono text-[11px] text-muted">{data.code ?? "—"}</p>
      <p className="truncate text-[11px] text-muted">
        {role ?? "—"}
        {data.inletW != null ? ` · ${formatKw(data.inletW)}` : ""}
        {data.mgmtIp ? ` · ${data.mgmtIp}` : data.hostname ? ` · ${data.hostname}` : ""}
      </p>
    </div>
  );
}

function CableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps<FlowEdge>) {
  const { te } = useI18n();
  const offset = data?.offset ?? 0;
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX: sourceX + offset,
    sourceY,
    targetX: targetX + offset,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  });
  const faulty = data?.status === "FAULTY";
  const fiber = data?.medium === "FIBER";
  const color = faulty
    ? "rgb(var(--danger))"
    : fiber
      ? "rgb(var(--accent))"
      : data?.relType
        ? "rgb(var(--text-muted))"
        : "rgb(var(--ok))";
  const caption = data?.relType
    ? te("relationType", data.relType)
    : data?.label || (data?.medium ? te("cableMedium", data.medium) : "");
  const title = [
    caption,
    data?.medium ? te("cableMedium", data.medium) : "",
    data?.status ? te("connectionStatus", data.status) : "",
    data?.lengthM != null ? `${data.lengthM} м` : "",
    data?.redundant ? "резерв" : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.4 : 1.6,
          strokeDasharray: data?.redundant ? "6 4" : undefined,
        }}
      />
      {caption && (
        <EdgeLabelRenderer>
          <div
            title={title}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            className="nodrag nopan pointer-events-auto absolute rounded border border-app bg-surface px-1 py-px text-[10px] text-muted"
          >
            {caption}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const diagramNodeTypes = { device: DeviceNode };
export const diagramEdgeTypes = { cable: CableEdge };
