import type { Edge, Node } from "@xyflow/react";

import type { DiagramEdge, DiagramNode } from "@/shared/api/types";

export const NODE_W = 220;
export const NODE_H = 86;

export interface DiagramNodeData extends Record<string, unknown> {
  label: string;
  code: string | null;
  role: string | null;
  status: string | null;
  criticality: string | null;
  hostname: string | null;
  mgmtIp: string | null;
  ciId: string | null;
  ciType: string | null;
}

export interface CableEdgeData extends Record<string, unknown> {
  label: string | null;
  medium: string | null;
  status: string | null;
  redundant: boolean;
  relType: string | null;
  lengthM: number | null;
  offset: number;
}

export type FlowNode = Node<DiagramNodeData, "device">;
export type FlowEdge = Edge<CableEdgeData, "cable">;

function facing(
  source: { x: number; y: number },
  target: { x: number; y: number },
): { sourceHandle: string; targetHandle: string } {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  if (Math.abs(dx) > Math.abs(dy) + 30) {
    return dx >= 0
      ? { sourceHandle: "out-right", targetHandle: "in-left" }
      : { sourceHandle: "out-left", targetHandle: "in-right" };
  }
  return dy >= 0
    ? { sourceHandle: "out-bottom", targetHandle: "in-top" }
    : { sourceHandle: "out-top", targetHandle: "in-bottom" };
}

export function toFlow(nodes: DiagramNode[], edges: DiagramEdge[]): {
  nodes: FlowNode[];
  edges: FlowEdge[];
} {
  const flowNodes: FlowNode[] = nodes.map((node) => ({
    id: node.id,
    type: "device",
    position: { x: node.x, y: node.y },
    data: {
      label: node.label,
      code: node.code,
      role: node.device_role,
      status: node.status,
      criticality: node.criticality,
      hostname: node.hostname,
      mgmtIp: node.mgmt_ip,
      ciId: node.ci_id,
      ciType: node.ci_type,
    },
  }));
  const byId = new Map(flowNodes.map((node) => [node.id, node]));
  const groups = new Map<string, DiagramEdge[]>();
  for (const edge of edges) {
    const key = [edge.source_node_id, edge.target_node_id].sort().join(":");
    const list = groups.get(key) ?? [];
    list.push(edge);
    groups.set(key, list);
  }
  const flowEdges: FlowEdge[] = [];
  for (const list of groups.values()) {
    list.forEach((edge, index) => {
      const source = byId.get(edge.source_node_id);
      const target = byId.get(edge.target_node_id);
      const handles =
        source && target ? facing(source.position, target.position) : {};
      flowEdges.push({
        id: edge.id,
        type: "cable",
        source: edge.source_node_id,
        target: edge.target_node_id,
        ...handles,
        data: {
          label: edge.label,
          medium: edge.medium,
          status: edge.status,
          redundant: edge.is_redundant,
          relType: edge.rel_type,
          lengthM: edge.length_m,
          offset: (index - (list.length - 1) / 2) * 16,
        },
      });
    });
  }
  return { nodes: flowNodes, edges: flowEdges };
}

export function retargetEdges(edges: FlowEdge[], nodes: FlowNode[]): FlowEdge[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return edges.map((edge) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) return edge;
    return { ...edge, ...facing(source.position, target.position) };
  });
}

function xml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function strokeFor(edge: FlowEdge): { color: string; dash: string } {
  if (edge.data?.status === "FAULTY") return { color: "#c53030", dash: "" };
  if (edge.data?.medium === "FIBER") {
    return { color: "#2563eb", dash: edge.data.redundant ? ' stroke-dasharray="6 4"' : "" };
  }
  if (edge.data?.relType) return { color: "#6b7280", dash: "" };
  return { color: "#16854e", dash: edge.data?.redundant ? ' stroke-dasharray="6 4"' : "" };
}

/** SVG текущей раскладки: то, что видно на экране, без обращения к серверу. */
export function diagramToSvg(name: string, nodes: FlowNode[], edges: FlowEdge[]): string {
  const pad = 36;
  if (nodes.length === 0) {
    return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="320" height="80" viewBox="0 0 320 80">
  <text x="16" y="44" font-family="sans-serif" font-size="14" fill="#68707a">${xml(name)}</text>
</svg>`;
  }
  const minX = Math.min(...nodes.map((node) => node.position.x)) - pad;
  const minY = Math.min(...nodes.map((node) => node.position.y)) - pad;
  const maxX = Math.max(...nodes.map((node) => node.position.x)) + NODE_W + pad;
  const maxY = Math.max(...nodes.map((node) => node.position.y)) + NODE_H + pad;
  const width = maxX - minX;
  const height = maxY - minY;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const lines = edges.flatMap((edge) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) return [];
    const x1 = source.position.x - minX + NODE_W / 2 + (edge.data?.offset ?? 0);
    const y1 = source.position.y - minY + NODE_H / 2;
    const x2 = target.position.x - minX + NODE_W / 2 + (edge.data?.offset ?? 0);
    const y2 = target.position.y - minY + NODE_H / 2;
    const { color, dash } = strokeFor(edge);
    const label = edge.data?.label ?? "";
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    return [
      `<path d="M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}" fill="none" stroke="${color}" stroke-width="1.6"${dash}/>`,
      label
        ? `<text x="${midX}" y="${midY - 4}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#68707a">${xml(label)}</text>`
        : "",
    ];
  });
  const cards = nodes.map((node) => {
    const x = node.position.x - minX;
    const y = node.position.y - minY;
    const title = xml(node.data.label);
    const code = node.data.code ? xml(node.data.code) : "";
    return `<g>
      <rect x="${x}" y="${y}" width="${NODE_W}" height="${NODE_H}" rx="6" fill="#ffffff" stroke="#e2e4e8"/>
      <text x="${x + 12}" y="${y + 28}" font-family="sans-serif" font-size="13" font-weight="600" fill="#181a20">${title}</text>
      <text x="${x + 12}" y="${y + 48}" font-family="ui-monospace,monospace" font-size="11" fill="#68707a">${code}</text>
      <text x="${x + 12}" y="${y + 68}" font-family="sans-serif" font-size="11" fill="#68707a">${xml(node.data.hostname ?? node.data.mgmtIp ?? "")}</text>
    </g>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#fafafa"/>
  <title>${xml(name)}</title>
  ${lines.join("\n  ")}
  ${cards.join("\n  ")}
</svg>`;
}

export function downloadSvg(filename: string, svg: string): void {
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
