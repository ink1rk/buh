import type { DiagramEdge, DiagramFull, DiagramNode } from "@/shared/api/types";
import { useI18n } from "@/i18n";

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

function nodeStroke(criticality: string | null): string {
  if (criticality === "CRITICAL") return "rgb(var(--danger))";
  if (criticality === "HIGH") return "rgb(var(--warn))";
  return "rgb(var(--border))";
}

function graphLayout(nodes: DiagramNode[], edges: DiagramEdge[]): Map<string, { x: number; y: number }> {
  const width = 640;
  const height = 300;
  const padX = 78;
  const padY = 42;
  const ids = nodes.map((node) => node.id);
  const adjacent = new Map<string, Set<string>>();
  for (const id of ids) adjacent.set(id, new Set());
  for (const edge of edges) {
    adjacent.get(edge.source_node_id)?.add(edge.target_node_id);
    adjacent.get(edge.target_node_id)?.add(edge.source_node_id);
  }
  let root = ids[0];
  let degree = -1;
  for (const id of ids) {
    const next = adjacent.get(id)?.size ?? 0;
    if (next > degree) {
      degree = next;
      root = id;
    }
  }
  const layer = new Map<string, number>();
  const queue = [root];
  layer.set(root, 0);
  while (queue.length > 0) {
    const id = queue.shift();
    if (!id) break;
    for (const next of adjacent.get(id) ?? []) {
      if (!layer.has(next)) {
        layer.set(next, (layer.get(id) ?? 0) + 1);
        queue.push(next);
      }
    }
  }
  let extra = Math.max(-1, ...layer.values()) + 1;
  for (const id of ids) {
    if (!layer.has(id)) layer.set(id, extra++);
  }
  const groups = new Map<number, string[]>();
  for (const [id, index] of layer) {
    const list = groups.get(index) ?? [];
    list.push(id);
    groups.set(index, list);
  }
  const layers = [...groups.keys()].sort((left, right) => left - right);
  const points = new Map<string, { x: number; y: number }>();
  layers.forEach((index, column) => {
    const list = groups.get(index) ?? [];
    const x = layers.length === 1 ? width / 2 : padX + (column / (layers.length - 1)) * (width - padX * 2);
    list.forEach((id, row) => {
      const y = list.length === 1 ? height / 2 : padY + (row / (list.length - 1)) * (height - padY * 2);
      points.set(id, { x, y });
    });
  });
  return points;
}

function place(nodes: DiagramNode[], edges: DiagramEdge[]): Map<string, { x: number; y: number }> {
  const width = 640;
  const height = 300;
  const padX = 64;
  const padY = 36;
  const xs = nodes.map((node) => node.x);
  const ys = nodes.map((node) => node.y);
  const flat = Math.max(...xs) - Math.min(...xs) < 48 || Math.max(...ys) - Math.min(...ys) < 48;
  if (flat) return graphLayout(nodes, edges);
  const points = new Map<string, { x: number; y: number }>();
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spread = maxX - minX > 8 || maxY - minY > 8;
  nodes.forEach((node, index) => {
    if (spread) {
      const sx = maxX === minX ? 0.5 : (node.x - minX) / (maxX - minX);
      const sy = maxY === minY ? 0.5 : (node.y - minY) / (maxY - minY);
      points.set(node.id, {
        x: padX + sx * (width - padX * 2),
        y: padY + sy * (height - padY * 2),
      });
      return;
    }
    const column = index % 4;
    const row = Math.floor(index / 4);
    points.set(node.id, { x: padX + column * 150, y: padY + row * 72 });
  });

  const ids = [...points.keys()];
  for (let pass = 0; pass < 10; pass += 1) {
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const a = points.get(ids[i]);
        const b = points.get(ids[j]);
        if (!a || !b) continue;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        const adx = Math.abs(dx);
        const ady = Math.abs(dy);
        if (adx < 112 && ady < 48) {
          if (dx === 0) dx = 1;
          if (dy === 0) dy = 1;
          a.x -= Math.sign(dx) * ((112 - adx) / 4 + 1);
          b.x += Math.sign(dx) * ((112 - adx) / 4 + 1);
          a.y -= Math.sign(dy) * ((48 - ady) / 4 + 1);
          b.y += Math.sign(dy) * ((48 - ady) / 4 + 1);
        }
      }
    }
  }
  for (const point of points.values()) {
    point.x = Math.min(width - padX, Math.max(padX, point.x));
    point.y = Math.min(height - padY, Math.max(padY, point.y));
  }
  return points;
}

function rim(
  from: { x: number; y: number },
  to: { x: number; y: number },
  halfW: number,
  halfH: number,
) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (dx === 0 && dy === 0) return from;
  const scale = Math.min(halfW / Math.abs(dx), halfH / Math.abs(dy), 1);
  return { x: from.x + dx * scale, y: from.y + dy * scale };
}

export function InfraMap({
  diagram,
  onOpen,
}: {
  diagram: DiagramFull;
  onOpen: (ciId: string) => void;
}) {
  const { te } = useI18n();
  const nodes = diagram.nodes.slice(0, 14);
  const ids = new Set(nodes.map((node) => node.id));
  const edges = diagram.edges.filter(
    (edge) => ids.has(edge.source_node_id) && ids.has(edge.target_node_id),
  );
  const points = place(nodes, edges);
  const kinds = new Set(
    edges.map((edge) =>
      edge.power_link_id ? "power" : edge.medium === "FIBER" ? "fiber" : edge.rel_type ? "logical" : "ethernet",
    ),
  );

  return (
    <div className="flex flex-col">
      <svg viewBox="0 0 640 300" className="h-72 w-full">
        <defs>
          <pattern id="itms-map-dots" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.8" fill="rgb(var(--border))" />
          </pattern>
        </defs>
        <rect width="640" height="300" fill="url(#itms-map-dots)" />
        {edges.map((edge, index) => {
          const from = points.get(edge.source_node_id);
          const to = points.get(edge.target_node_id);
          if (!from || !to) return null;
          const start = rim(from, to, 52, 18);
          const end = rim(to, from, 52, 18);
          const dx = end.x - start.x;
          const dy = end.y - start.y;
          const len = Math.hypot(dx, dy) || 1;
          const bow = ((index % 3) - 1) * 16;
          const mx = (start.x + end.x) / 2 + (-dy / len) * bow;
          const my = (start.y + end.y) / 2 + (dx / len) * bow;
          const stroke = edgeStroke(edge);
          return (
            <path
              key={edge.id}
              d={`M ${start.x} ${start.y} Q ${mx} ${my} ${end.x} ${end.y}`}
              fill="none"
              stroke={stroke.color}
              strokeWidth={1.75}
              strokeDasharray={stroke.dash}
            />
          );
        })}
        {nodes.map((node) => {
          const point = points.get(node.id);
          if (!point) return null;
          const label = (node.code ?? node.label).slice(0, 12);
          return (
            <g
              key={node.id}
              className={node.ci_id ? "cursor-pointer" : undefined}
              onClick={() => node.ci_id && onOpen(node.ci_id)}
            >
              <rect
                x={point.x - 50}
                y={point.y - 16}
                width={100}
                height={32}
                rx={9}
                fill="rgb(var(--surface))"
                stroke={nodeStroke(node.criticality)}
              />
              <circle cx={point.x - 36} cy={point.y} r={3.5} fill={statusFill(node.status)} />
              <text
                x={point.x - 26}
                y={point.y + 4}
                fill="rgb(var(--text))"
                fontSize={11}
                fontFamily="IBM Plex Mono, ui-monospace, monospace"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-4 px-1 pt-2 text-[11px] text-muted">
        {kinds.has("ethernet") && <Legend color="rgb(var(--accent))" label={te("diagramType", "NETWORK")} />}
        {kinds.has("fiber") && <Legend color="rgb(var(--ok))" label={te("cableMedium", "FIBER")} />}
        {kinds.has("power") && <Legend color="rgb(var(--warn))" label={te("diagramType", "POWER")} />}
        {kinds.has("logical") && (
          <Legend color="rgb(var(--accent))" dashed label={te("diagramType", "LOGICAL")} />
        )}
      </div>
    </div>
  );
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="22" height="8" aria-hidden>
        <line
          x1="1"
          y1="4"
          x2="21"
          y2="4"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={dashed ? "3 2" : undefined}
        />
      </svg>
      {label}
    </span>
  );
}
