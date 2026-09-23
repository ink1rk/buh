import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useDashboard, useDiagram, useDiagrams, useInbox, usePower, useProjects, useSession, useTransition } from "@/shared/api/queries";
import type { InboxItem, PowerNodeRow, PowerOverview, ProjectSummary } from "@/shared/api/types";
import { formatRelative } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { EmptyState, Spinner } from "@/shared/ui/Layout";

import { InfraMap } from "./InfraMap";

const AUTH_ACTIONS = new Set(["LOGIN", "LOGOUT", "LOGIN_FAILED"]);
const WORK_BUCKETS = ["overdue", "today", "upcoming", "undated", "later"] as const;
const CRIT_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

function greetingKey(hour: number): "dashboard.greetingMorning" | "dashboard.greetingDay" | "dashboard.greetingEvening" {
  if (hour < 12) return "dashboard.greetingMorning";
  if (hour < 18) return "dashboard.greetingDay";
  return "dashboard.greetingEvening";
}

function bucketKey(bucket: string): "projects.overdue" | "projects.today" | "projects.upcoming" | "projects.undated" | "projects.later" {
  if (bucket === "overdue") return "projects.overdue";
  if (bucket === "today") return "projects.today";
  if (bucket === "upcoming") return "projects.upcoming";
  if (bucket === "undated") return "projects.undated";
  return "projects.later";
}

function critBar(key: string): string {
  if (key === "CRITICAL") return "bg-[rgb(var(--danger))]";
  if (key === "HIGH") return "bg-[rgb(var(--warn))]";
  if (key === "MEDIUM") return "bg-[rgb(var(--accent))]";
  return "bg-[rgb(var(--text-muted))]";
}

function critStroke(key: string): string {
  if (key === "CRITICAL") return "rgb(var(--danger))";
  if (key === "HIGH") return "rgb(var(--warn))";
  if (key === "MEDIUM") return "rgb(var(--accent))";
  return "rgb(var(--text-muted))";
}

function Ring({
  total,
  segments,
}: {
  total: number;
  segments: Array<{ key: string; count: number }>;
}) {
  const radius = 52;
  const length = 2 * Math.PI * radius;
  const gap = segments.filter((segment) => segment.count > 0).length > 1 ? 7 : 0;
  let offset = 0;
  const sum = segments.reduce((acc, segment) => acc + segment.count, 0) || 1;
  const critical = segments.find((segment) => segment.key === "CRITICAL")?.count ?? 0;
  const high = segments.find((segment) => segment.key === "HIGH")?.count ?? 0;
  const glow = total <= 0 ? "" : critical > 0 ? "glow-danger" : high > 0 ? "glow-warn" : "glow-ok";
  return (
    <svg viewBox="0 0 148 148" className={`h-40 w-40 shrink-0 ${glow}`}>
      <circle cx="74" cy="74" r={radius} fill="none" stroke="rgb(var(--bg))" strokeWidth="14" />
      {segments.map((segment) => {
        const arc = (segment.count / sum) * length;
        const draw = Math.max(arc - gap, segment.count > 0 ? 2 : 0);
        const node = (
          <circle
            key={segment.key}
            cx="74"
            cy="74"
            r={radius}
            fill="none"
            stroke={critStroke(segment.key)}
            strokeWidth="14"
            strokeLinecap="butt"
            strokeDasharray={`${draw} ${length - draw}`}
            strokeDashoffset={-offset}
            transform="rotate(-90 74 74)"
          />
        );
        offset += arc;
        return node;
      })}
      <text x="74" y="82" textAnchor="middle" fill="rgb(var(--text))" fontSize="36" fontWeight="650">
        {total}
      </text>
    </svg>
  );
}

function primaryPath(nodes: PowerNodeRow[], links: PowerOverview["links"], primaryId: string | null | undefined): PowerNodeRow[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const children = new Map<string, string[]>();
  for (const link of links) {
    const list = children.get(link.source_node_id) ?? [];
    list.push(link.target_node_id);
    children.set(link.source_node_id, list);
  }
  const start = primaryId ?? nodes.find((node) => node.node_type === "INPUT")?.id;
  if (!start) return [];

  const walk = (id: string, seen: Set<string>): PowerNodeRow[] => {
    const node = byId.get(id);
    if (!node || seen.has(id)) return [];
    const nextSeen = new Set(seen);
    nextSeen.add(id);
    let best: PowerNodeRow[] = [];
    for (const child of children.get(id) ?? []) {
      const tail = walk(child, nextSeen);
      if (tail.length > best.length) best = tail;
    }
    return [node, ...best];
  };

  return walk(start, new Set()).slice(0, 6);
}

function ChainSketch({ nodes, onOpen }: { nodes: PowerNodeRow[]; onOpen: (id: string) => void }) {
  if (nodes.length < 2) return null;
  const perRow = nodes.length > 4 ? Math.ceil(nodes.length / 2) : nodes.length;
  const step = 78;
  const width = 28 + Math.max(perRow - 1, 0) * step + 28;
  const rows = Math.ceil(nodes.length / perRow);
  const height = rows === 1 ? 62 : 112;
  const pos = (index: number) => {
    const row = Math.floor(index / perRow);
    const col = index % perRow;
    const visual = row % 2 === 1 ? perRow - 1 - col : col;
    return { x: 28 + visual * step, y: 14 + row * 52 };
  };
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-3 w-full" style={{ height: rows === 1 ? 72 : 124 }}>
      {nodes.map((node, index) => {
        if (index === 0) return null;
        const from = pos(index - 1);
        const to = pos(index);
        return (
          <line
            key={`${node.id}-link`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke="rgb(var(--accent))"
            strokeWidth="1.5"
          />
        );
      })}
      {nodes.map((node, index) => {
        const point = pos(index);
        const label = (node.code ?? node.name).slice(0, 8);
        return (
          <g key={node.id} className="cursor-pointer" onClick={() => onOpen(node.id)}>
            <circle cx={point.x} cy={point.y} r="8" fill="rgb(var(--bg))" stroke="rgb(var(--accent))" strokeWidth="1.6" />
            <circle cx={point.x} cy={point.y} r="2.4" fill="rgb(var(--accent))" />
            <text
              x={point.x}
              y={point.y + 22}
              textAnchor="middle"
              fill="rgb(var(--text-muted))"
              fontSize="10"
              fontFamily="IBM Plex Mono, ui-monospace, monospace"
            >
              {label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function AttentionCard({
  value,
  label,
  tone,
  ratio,
  onClick,
}: {
  value: number;
  label: string;
  tone: "danger" | "warn" | "accent" | "ok";
  ratio?: number;
  onClick: () => void;
}) {
  const hot = value > 0;
  const wash =
    tone === "danger"
      ? hot
        ? "border-[rgb(var(--danger)/0.5)] bg-[rgb(var(--danger)/0.2)]"
        : "border-[rgb(var(--danger)/0.4)] bg-[rgb(var(--danger)/0.14)]"
      : tone === "warn"
        ? hot
          ? "border-[rgb(var(--warn)/0.5)] bg-[rgb(var(--warn)/0.22)]"
          : "border-[rgb(var(--warn)/0.4)] bg-[rgb(var(--warn)/0.16)]"
        : tone === "ok"
          ? hot
            ? "border-[rgb(var(--ok)/0.5)] bg-[rgb(var(--ok)/0.2)]"
            : "border-[rgb(var(--ok)/0.4)] bg-[rgb(var(--ok)/0.14)]"
          : hot
            ? "border-[rgb(var(--accent)/0.5)] bg-[rgb(var(--accent)/0.2)]"
            : "border-[rgb(var(--accent)/0.4)] bg-[rgb(var(--accent)/0.14)]";
  const number = !hot
    ? "text-app"
    : tone === "danger"
      ? "text-[rgb(var(--danger))]"
      : tone === "warn"
        ? "text-[rgb(var(--warn))]"
        : tone === "ok"
          ? "text-[rgb(var(--ok))]"
          : "text-[rgb(var(--accent))]";
  const arc = ratio == null ? 0 : Math.max(0, Math.min(1, ratio));
  const turn = 2 * Math.PI * 26;
  const stripe =
    tone === "danger"
      ? "bg-[rgb(var(--danger))]"
      : tone === "warn"
        ? "bg-[rgb(var(--warn))]"
        : tone === "ok"
          ? "bg-[rgb(var(--ok))]"
          : "bg-[rgb(var(--accent))]";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`card relative min-h-[6.75rem] overflow-hidden px-4 py-4 text-left transition-transform hover:-translate-y-px ${wash}`}
    >
      <span className={`absolute inset-y-4 left-0 w-1 rounded-r-full ${stripe}`} />
      {ratio != null && (
        <svg viewBox="0 0 72 72" className={`pointer-events-none absolute -right-2 -bottom-3 h-20 w-20 ${number}`} aria-hidden>
          <circle cx="36" cy="36" r="26" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="6" />
          <circle
            cx="36"
            cy="36"
            r="26"
            fill="none"
            stroke="currentColor"
            strokeWidth="6"
            strokeDasharray={`${arc * turn} ${turn}`}
            transform="rotate(-90 36 36)"
          />
        </svg>
      )}
      <p className={`relative text-4xl leading-none font-semibold tracking-tight tabular-nums ${number}`}>{value}</p>
      <p className="relative mt-3 max-w-[11rem] text-[13px] leading-snug font-medium">{label}</p>
    </button>
  );
}

function ProjectRow({
  project,
  health,
  onOpen,
}: {
  project: ProjectSummary;
  health: string;
  onOpen: () => void;
}) {
  const tone = project.health === "ON_TRACK" ? "ok" : project.health === "DELAYED" ? "danger" : "warn";
  return (
    <button type="button" onClick={onOpen} className="w-full px-4 py-3 text-left hover:bg-[rgb(var(--surface-muted))]">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{project.name}</span>
          <span className="mt-0.5 block text-xs text-muted">
            <span className="font-mono">{project.key}</span>
            {project.owner_name ? ` · ${project.owner_name}` : ""}
            {project.due_date ? ` · ${project.due_date}` : ""}
          </span>
        </span>
        <span className="text-2xl leading-none font-semibold tracking-tight tabular-nums">{project.progress_pct}%</span>
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-[rgb(var(--bg))]">
          <div
            className="h-full rounded-full bg-[rgb(var(--accent))]"
            style={{ width: `${Math.min(project.progress_pct, 100)}%` }}
          />
        </div>
        <Badge tone={tone}>{health}</Badge>
      </div>
    </button>
  );
}

function CardTitle({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex items-center justify-between gap-3 px-4 pt-4 pb-1">
      <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      {action}
    </header>
  );
}

function actionDot(action: string): string {
  if (action === "CREATE") return "bg-[rgb(var(--ok))]";
  if (action === "DELETE" || action === "ARCHIVE") return "bg-[rgb(var(--danger))]";
  return "bg-[rgb(var(--accent))]";
}

export function DashboardPage() {
  const { t, te, locale } = useI18n();
  const navigate = useNavigate();
  const { data: session } = useSession();
  const { data, isPending } = useDashboard();
  const inbox = useInbox();
  const projects = useProjects();
  const power = usePower();
  const diagrams = useDiagrams();
  const featuredId = (projects.data ?? []).find(
    (project) => project.status !== "COMPLETED" && project.status !== "CANCELLED",
  )?.id;
  const transition = useTransition(featuredId);
  const mapSummary =
    (diagrams.data ?? []).find((item) => item.diagram_type === "NETWORK") ??
    (diagrams.data ?? []).find((item) => item.diagram_type === "LOGICAL") ??
    diagrams.data?.[0];
  const map = useDiagram(mapSummary?.id);

  if (isPending || !data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const name = (session?.display_name ?? "").trim().split(/\s+/)[0] || t("app.name");
  const today = new Date();
  const todayKey = today.toISOString().slice(0, 10);
  const changes = data.recent_activity.filter((item) => !AUTH_ACTIONS.has(item.action));
  const changesToday = changes.filter((item) => item.occurred_at.slice(0, 10) === todayKey).length;
  const feed = (changes.length > 0 ? changes : data.recent_activity).slice(0, 5);
  const tasks = inbox.data ?? [];
  const overdue = tasks.filter((item) => item.bucket === "overdue");
  const myWork = WORK_BUCKETS.flatMap((bucket) => tasks.filter((item) => item.bucket === bucket)).slice(0, 6);
  const active = (projects.data ?? []).filter(
    (project) => project.status !== "COMPLETED" && project.status !== "CANCELLED",
  );
  const inputs = (power.data?.nodes ?? []).filter((node) => node.node_type === "INPUT");
  const primary = [...inputs].sort(
    (left, right) => right.inlet_w - left.inlet_w || (left.code ?? "").localeCompare(right.code ?? ""),
  )[0];
  const chain = primaryPath(power.data?.nodes ?? [], power.data?.links ?? [], power.data?.primary_input_id);
  const quality = data.data_quality;
  const coverage = quality.provenance.coverage_pct as number;
  const criticality = CRIT_ORDER.map((key) => data.ci_by_criticality.find((row) => row.key === key)).filter(
    (row): row is { key: string; count: number } => Boolean(row),
  );
  const critSum = criticality.reduce((acc, row) => acc + row.count, 0) || 1;
  const headroomKw =
    primary?.headroom_w == null
      ? null
      : primary.headroom_w / 1000;
  const deficitW = transition.data?.live.deficit_w ?? 0;
  const openTask = (item: InboxItem) => navigate(`/projects/${item.project_id}?task=${item.id}`);
  const linkClass = "text-xs text-accent";

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t(greetingKey(today.getHours()), { name })}</h1>
          <p className="mt-1 text-sm text-muted">{t("dashboard.subtitle")}</p>
        </div>
        <p className="text-sm text-muted">
          {new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" }).format(today)}
        </p>
      </header>

      <section>
        <h2 className="mb-2 px-1 text-[13px] font-medium text-muted">{t("dashboard.attention")}</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <AttentionCard
            value={data.counters.ci_critical}
            label={t("dashboard.ciCritical")}
            tone="danger"
            ratio={data.counters.ci_total > 0 ? data.counters.ci_critical / data.counters.ci_total : undefined}
            onClick={() => navigate("/ci?criticality=CRITICAL")}
          />
          <AttentionCard
            value={overdue.length}
            label={t("dashboard.overdueTasks")}
            tone="warn"
            ratio={tasks.length > 0 ? overdue.length / tasks.length : undefined}
            onClick={() => navigate("/work")}
          />
          <AttentionCard
            value={data.counters.ci_attention}
            label={t("dashboard.ciAttention")}
            tone="accent"
            ratio={data.counters.ci_total > 0 ? data.counters.ci_attention / data.counters.ci_total : undefined}
            onClick={() => navigate("/ci?status=DEGRADED")}
          />
          <AttentionCard
            value={changesToday}
            label={t("dashboard.changesToday")}
            tone="ok"
            onClick={() => navigate("/audit")}
          />
        </div>
      </section>

      <div className="grid gap-3 xl:grid-cols-[1.15fr_1fr_0.92fr]">
        <section className="card">
          <CardTitle
            title={t("dashboard.healthTitle")}
            action={<Link to="/infrastructure" className={linkClass}>{t("dashboard.showAll")}</Link>}
          />
          <div className="flex items-center gap-2 px-3 pt-1 pb-2">
            <div className="flex flex-col items-center">
              <Ring total={data.counters.ci_total} segments={criticality} />
              <p className="-mt-1 text-[11px] text-muted">{t("dashboard.ciTotal")}</p>
            </div>
            <ul className="flex min-w-0 flex-1 flex-col gap-2.5 pr-3">
              {criticality.map((row) => (
                <li key={row.key}>
                  <div className="flex items-baseline gap-2 text-sm">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${critBar(row.key)}`} />
                    <span className="truncate text-muted">{te("criticality", row.key)}</span>
                    <span className="ml-auto text-lg leading-none font-semibold tabular-nums">{row.count}</span>
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[rgb(var(--bg))]">
                    <div className={`h-full rounded-full ${critBar(row.key)}`} style={{ width: `${(row.count / critSum) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="mx-4 border-t border-app" />
          <div className="grid grid-cols-3 gap-2 px-4 py-3">
            {[
              [t("dashboard.withoutOwner"), quality.ci_without_owner, "/ci?missing=owner"],
              [t("dashboard.withoutLocation"), quality.ci_without_location, "/ci?missing=location"],
              [t("dashboard.documentsReview"), data.counters.documents_review_due, "/documents"],
            ].map(([label, value, href]) => (
              <Link key={String(href)} to={String(href)} className="rounded-lg px-1 py-1 hover:bg-[rgb(var(--surface-muted))]">
                <span className={`block text-xl leading-none font-semibold tabular-nums ${Number(value) > 0 ? "text-[rgb(var(--warn))]" : "text-muted"}`}>
                  {value}
                </span>
                <span className="mt-1 block text-[11px] leading-snug text-muted">{label}</span>
              </Link>
            ))}
          </div>
        </section>

        <section className="card overflow-hidden">
          <CardTitle
            title={t("dashboard.activeProjects")}
            action={<Link to="/projects" className={linkClass}>{t("dashboard.showAll")}</Link>}
          />
          {active.length === 0 ? (
            <EmptyState title={t("dashboard.noProjects")} hint={t("dashboard.noProjectsHint")} />
          ) : (
            <ul className="pb-1">
              {active.slice(0, 4).map((project) => (
                <li key={project.id} className="border-b border-app last:border-0">
                  <ProjectRow
                    project={project}
                    health={te("health", project.health)}
                    onOpen={() => navigate(`/projects/${project.id}`)}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card overflow-hidden">
          <CardTitle
            title={t("dashboard.myWork")}
            action={<Link to="/work" className={linkClass}>{t("dashboard.showAll")}</Link>}
          />
          {myWork.length === 0 ? (
            <EmptyState title={t("dashboard.noTasks")} hint={t("dashboard.noTasksHint")} />
          ) : (
            <ul>
              {myWork.map((item) => (
                <li key={item.id} className="border-b border-app last:border-0">
                  <button
                    type="button"
                    onClick={() => openTask(item)}
                    className="flex w-full items-stretch gap-3 px-4 py-2.5 text-left hover:bg-[rgb(var(--surface-muted))]"
                  >
                    <span
                      className={`my-0.5 w-0.5 shrink-0 rounded-full ${
                        item.bucket === "overdue"
                          ? "bg-[rgb(var(--danger))]"
                          : item.bucket === "today"
                            ? "bg-[rgb(var(--accent))]"
                            : "bg-[rgb(var(--border))]"
                      }`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{item.title}</span>
                      <span className="mt-0.5 block text-xs text-muted">
                        <span className="font-mono">{item.label}</span>
                        {" · "}
                        {item.project_key}
                        {item.due_date ? ` · ${item.due_date}` : ""}
                      </span>
                    </span>
                    <Badge tone={item.bucket === "overdue" ? "danger" : item.bucket === "today" ? "accent" : "neutral"}>
                      {t(bucketKey(item.bucket))}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.78fr)]">
        <section className="card flex flex-col overflow-hidden">
          <CardTitle
            title={t("nav.infrastructure")}
            action={
              mapSummary ? (
                <Link to={`/diagrams/${mapSummary.id}`} className={linkClass}>{t("dashboard.openMap")}</Link>
              ) : (
                <Link to="/diagrams" className={linkClass}>{t("dashboard.openMap")}</Link>
              )
            }
          />
          <div className="flex-1 px-3 pt-1 pb-3">
            <div className="h-full overflow-hidden rounded-xl bg-[rgb(var(--bg))] px-2 py-2">
              {map.data && map.data.nodes.length > 0 ? (
                <InfraMap diagram={map.data} onOpen={(ciId) => navigate(`/ci/${ciId}`)} />
              ) : (
                <EmptyState
                  title={t("app.empty")}
                  action={<Link to="/diagrams" className="text-sm text-accent">{t("dashboard.openMap")}</Link>}
                />
              )}
            </div>
          </div>
        </section>

        <section className="card px-4 pt-4 pb-4">
          <header className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold tracking-tight">{t("nav.power")}</h2>
            <Link to="/power" className={linkClass}>{t("dashboard.openPower")}</Link>
          </header>
          {primary ? (
            <>
              <p className="mt-3 font-mono text-xs text-muted">{primary.code ?? primary.name}</p>
              <p className="mt-1 flex items-baseline gap-2">
                <span
                  className={`text-6xl leading-none font-semibold tracking-tight tabular-nums ${
                    headroomKw != null && headroomKw < 0 ? "text-[rgb(var(--danger))]" : ""
                  }`}
                >
                  {headroomKw == null
                    ? "—"
                    : headroomKw.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                </span>
                <span className="text-sm text-muted">кВт</span>
              </p>
              <p className="mt-1 text-xs text-muted">{t("dashboard.powerHeadroom")}</p>
              <div className="mt-4 flex items-center justify-between font-mono text-[11px] text-muted tabular-nums">
                <span>{primary.inlet_w} Вт</span>
                <span>{primary.limit_w ?? "—"} Вт</span>
              </div>
              <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-[rgb(var(--bg))]">
                <div
                  className={`h-full rounded-full ${headroomKw != null && headroomKw < 0 ? "bg-[rgb(var(--danger))]" : "bg-[rgb(var(--ok))]"}`}
                  style={{
                    width: `${primary.limit_w ? Math.min(100, (primary.inlet_w / primary.limit_w) * 100) : 0}%`,
                  }}
                />
              </div>
              {primary.failover && (
                <p className="mt-2 text-xs text-muted">{te("failover", primary.failover)}</p>
              )}
              {deficitW > 0 && (
                <p className="mt-3 inline-flex items-baseline gap-2 rounded-lg bg-[rgb(var(--danger)/0.14)] px-2.5 py-1.5 text-[rgb(var(--danger))]">
                  <span className="text-lg font-semibold tabular-nums">
                    {(deficitW / 1000).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                  </span>
                  <span className="text-xs">{t("power.deficit")}, кВт</span>
                </p>
              )}
              <ChainSketch nodes={chain} onOpen={(id) => navigate(`/ci/${id}`)} />
            </>
          ) : (
            <EmptyState title={t("dashboard.noPower")} action={<Link to="/power" className="text-sm text-accent">{t("dashboard.openPower")}</Link>} />
          )}
        </section>

        <section className="card overflow-hidden xl:col-span-2">
          <CardTitle
            title={t("dashboard.activity")}
            action={<Link to="/audit" className={linkClass}>{t("dashboard.showAll")}</Link>}
          />
          {feed.length === 0 ? (
            <EmptyState title={t("app.empty")} />
          ) : (
            <ul className="grid pb-1 sm:grid-cols-2">
              {feed.map((item) => {
                const href =
                  item.entity_type === "CI" && item.entity_id
                    ? `/ci/${item.entity_id}`
                    : item.entity_type === "PROJECT" && item.entity_id
                      ? `/projects/${item.entity_id}`
                      : item.project_id
                        ? `/projects/${item.project_id}`
                        : null;
                const change = item.changes?.[0];
                const body = (
                  <>
                    <span className="block truncate text-sm font-medium">{item.entity_label ?? te("entityType", item.entity_type)}</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {te("auditAction", item.action)}
                      {change ? ` · ${change.field}: ${change.old_value ?? "—"} → ${change.new_value ?? "—"}` : ""}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted">
                      {item.actor_label ? `${item.actor_label} · ` : ""}
                      {formatRelative(item.occurred_at, locale)}
                    </span>
                  </>
                );
                return (
                  <li key={item.id} className="relative border-b border-app last:border-0 sm:[&:nth-last-child(-n+2)]:border-0">
                    <span className={`absolute top-3.5 left-4 h-2 w-2 rounded-full ${actionDot(item.action)}`} />
                    {href ? (
                      <Link to={href} className="block py-2.5 pr-4 pl-9 hover:bg-[rgb(var(--surface-muted))]">{body}</Link>
                    ) : (
                      <div className="py-2.5 pr-4 pl-9">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <section className="card px-4 py-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold tracking-tight">{t("dashboard.dataQuality")}</h2>
            <p className="mt-0.5 text-xs text-muted">{t("dashboard.provenanceCoverage")}</p>
          </div>
          <p className="text-3xl leading-none font-semibold tracking-tight tabular-nums">{Math.round(coverage)}%</p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-[rgb(var(--bg))]">
          <div className="h-full rounded-full bg-[rgb(var(--accent))]" style={{ width: `${Math.min(coverage, 100)}%` }} />
        </div>
      </section>
    </div>
  );
}
