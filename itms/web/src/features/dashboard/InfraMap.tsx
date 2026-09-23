import type { DiagramEdge, DiagramFull, DiagramNode } from "@/shared/api/types";

function edgeStroke(edge: DiagramEdge): { color: string; dash?: string } {
  if (edge.power_link_id) return { color: "rgb(var(--warn))" };
  if (edge.medium === "FIBER") return { color: "rgb(var(--ok))" };
  if (edge.rel_type || edge.relation_id) return { color: "rgb(var(--accent))", dash: "4 3" };
  return { color: "rgb(var(--accent))" };
}

function statusFill(status: string | null): string {
  if (status === "DEGRADED" || status === "RETIRED") return "rgb(var(--danger))";
  if (status === "MAINTENANCE" || status === "PLANNED") return "rgb(var(--warn))";
  return "rgb(var(--ok))";
}

function place(nodes: DiagramNode[]): Map<string, { x: number; y: number }> {
  const width = 460;
  const height = 220;
  const pad = 28;
  const points = new Map<string, { x: number; y: number }>();
  const xs = nodes.map((node) => node.x);
  const ys = nodes.map((node) => node.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spread = maxX - minX > 8 || maxY - minY > 8;
  nodes.forEach((node, index) => {
    if (spread) {
      const sx = maxX === minX ? 0.5 : (node.x - minX) / (maxX - minX);
      const sy = maxY === minY ? 0.5 : (node.y - minY) / (maxY - minY);
      points.set(node.id, { x: pad + sx * (width - pad * 2), y: pad + sy * (height - pad * 2) });
      return;
    }
    const column = index % 4;
    const row = Math.floor(index / 4);
    points.set(node.id, { x: pad + column * 110, y: pad + row * 52 });
  });
  return points;
}

export function InfraMap({
  diagram,
  onOpen,
}: {
  diagram: DiagramFull;
  onOpen: (ciId: string) => void;
}) {
  const nodes = diagram.nodes.slice(0, 18);
  const ids = new Set(nodes.map((node) => node.id));
  const edges = diagram.edges.filter(
    (edge) => ids.has(edge.source_node_id) && ids.has(edge.target_node_id),
  );
  const points = place(nodes);
  const kinds = new Set(edges.map((edge) => (edge.power_link_id ? "power" : edge.medium === "FIBER" ? "fiber" : edge.rel_type ? "logical" : "ethernet")));

  return (
    <div>
      <svg viewBox="0 0 460 220" className="h-56 w-full">
        {edges.map((edge) => {
          const from = points.get(edge.source_node_id);
          const to = points.get(edge.target_node_id);
          if (!from || !to) return null;
          const stroke = edgeStroke(edge);
          return (
            <line
              key={edge.id}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={stroke.color}
              strokeWidth={1.4}
              strokeDasharray={stroke.dash}
            />
          );
        })}
        {nodes.map((node) => {
          const point = points.get(node.id);
          if (!point) return null;
          const label = node.code ?? node.label;
          return (
            <g
              key={node.id}
              transform={`translate(${point.x}, ${point.y})`}
              className={node.ci_id ? "cursor-pointer" : undefined}
              onClick={() => node.ci_id && onOpen(node.ci_id)}
            >
              <circle r={4} cy={-10} fill={statusFill(node.status)} />
              <text textAnchor="middle" y={4} fill="rgb(var(--text))" fontSize={10} fontFamily="IBM Plex Mono, ui-monospace, monospace">
                {label.length > 14 ? `${label.slice(0, 13)}…` : label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
        {kinds.has("ethernet") && <span className="text-[rgb(var(--accent))]">— Ethernet</span>}
        {kinds.has("fiber") && <span className="text-[rgb(var(--ok))]">— Fiber</span>}
        {kinds.has("power") && <span className="text-[rgb(var(--warn))]">— Power</span>}
        {kinds.has("logical") && <span className="text-[rgb(var(--accent))]">- - Logical</span>}
      </div>
    </div>
  );
}
