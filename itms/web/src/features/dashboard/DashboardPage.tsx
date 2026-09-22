import { Link, useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useDashboard, useDiagrams, useInbox, usePower, useProjects, useSession } from "@/shared/api/queries";
import type { InboxItem, PowerNodeRow, PowerOverview, ProjectSummary } from "@/shared/api/types";
import { formatRelative } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { EmptyState, Panel, Spinner } from "@/shared/ui/Layout";

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

  return walk(start, new Set()).slice(0, 7);
}

function AttentionCard({
  value,
  label,
  hint,
  hot,
  onClick,
}: {
  value: number;
  label: string;
  hint?: string;
  hot: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="surface rounded-lg px-3.5 py-3 text-left transition-colors hover:bg-[rgb(var(--surface-muted))]"
    >
      <p className={`text-2xl leading-none font-semibold tabular-nums ${hot ? "text-[rgb(var(--danger))]" : "text-app"}`}>
        {value}
      </p>
      <p className="mt-2 text-[13px] font-medium">{label}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
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
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{project.name}</span>
          <span className="mt-0.5 block text-xs text-muted">
            <span className="font-mono">{project.key}</span>
            {project.owner_name ? ` · ${project.owner_name}` : ""}
            {project.due_date ? ` · ${project.due_date}` : ""}
            {` · ${project.open_task_count}/${project.task_count}`}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <Badge tone={tone}>{health}</Badge>
          <span className="text-sm font-semibold tabular-nums">{project.progress_pct}%</span>
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-[rgb(var(--surface-muted))]">
        <div
          className="h-full rounded-full bg-[rgb(var(--accent))]"
          style={{ width: `${Math.min(project.progress_pct, 100)}%` }}
        />
      </div>
    </button>
  );
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
  const feed = (changes.length > 0 ? changes : data.recent_activity).slice(0, 7);
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
  const powerDiagram = (diagrams.data ?? []).find((item) => item.diagram_type === "POWER") ?? diagrams.data?.[0];
  const chain = primaryPath(power.data?.nodes ?? [], power.data?.links ?? [], power.data?.primary_input_id);
  const quality = data.data_quality;
  const coverage = quality.provenance.coverage_pct as number;
  const criticality = CRIT_ORDER.map((key) => data.ci_by_criticality.find((row) => row.key === key)).filter(
    (row): row is { key: string; count: number } => Boolean(row),
  );

  const openTask = (item: InboxItem) => navigate(`/projects/${item.project_id}?task=${item.id}`);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t(greetingKey(today.getHours()), { name })}</h1>
          <p className="mt-1 text-sm text-muted">{t("dashboard.subtitle")}</p>
        </div>
        <p className="text-sm text-muted">
          {new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" }).format(today)}
        </p>
      </header>

      <section>
        <h2 className="mb-2 text-[13px] font-medium text-muted">{t("dashboard.attention")}</h2>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          <AttentionCard
            value={data.counters.ci_critical}
            label={t("dashboard.ciCritical")}
            hot={data.counters.ci_critical > 0}
            onClick={() => navigate("/ci?criticality=CRITICAL")}
          />
          <AttentionCard
            value={overdue.length}
            label={t("dashboard.overdueTasks")}
            hot={overdue.length > 0}
            onClick={() => navigate("/work")}
          />
          <AttentionCard
            value={data.counters.ci_attention}
            label={t("dashboard.ciAttention")}
            hot={data.counters.ci_attention > 0}
            onClick={() => navigate("/ci?status=DEGRADED")}
          />
          <AttentionCard
            value={quality.ci_without_owner}
            label={t("dashboard.withoutOwner")}
            hot={quality.ci_without_owner > 0}
            onClick={() => navigate("/ci?missing=owner")}
          />
          <AttentionCard
            value={changesToday}
            label={t("dashboard.changesToday")}
            hot={false}
            onClick={() => navigate("/audit")}
          />
          <AttentionCard
            value={data.counters.documents_review_due}
            label={t("dashboard.documentsReview")}
            hot={data.counters.documents_review_due > 0}
            onClick={() => navigate("/documents")}
          />
        </div>
      </section>

      <div className="grid gap-3 xl:grid-cols-[1.1fr_0.9fr]">
        <Panel title={t("dashboard.myWork")} bodyClassName="p-0" actions={<Link to="/work" className="text-xs text-accent">{t("dashboard.showAll")}</Link>}>
          {myWork.length === 0 ? (
            <EmptyState title={t("dashboard.noTasks")} hint={t("dashboard.noTasksHint")} />
          ) : (
            <ul>
              {myWork.map((item) => (
                <li key={item.id} className="border-b border-app last:border-0">
                  <button
                    type="button"
                    onClick={() => openTask(item)}
                    className="flex w-full items-start justify-between gap-3 px-4 py-2.5 text-left hover:bg-[rgb(var(--surface-muted))]"
                  >
                    <span className="min-w-0">
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
        </Panel>

        <Panel title={t("dashboard.activeProjects")} bodyClassName="p-0" actions={<Link to="/projects" className="text-xs text-accent">{t("dashboard.showAll")}</Link>}>
          {active.length === 0 ? (
            <EmptyState title={t("dashboard.noProjects")} hint={t("dashboard.noProjectsHint")} />
          ) : (
            <ul>
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
        </Panel>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <Panel title={t("dashboard.healthTitle")}>
          <div className="flex items-end justify-between">
            <p className="text-3xl font-semibold tabular-nums tracking-tight">{data.counters.ci_total}</p>
            <p className="text-xs text-muted">{t("dashboard.ciTotal")}</p>
          </div>
          <ul className="mt-3 flex flex-col gap-2">
            {criticality.map((row) => (
              <li key={row.key}>
                <div className="mb-1 flex justify-between text-xs">
                  <span>{te("criticality", row.key)}</span>
                  <span className="tabular-nums text-muted">{row.count}</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-[rgb(var(--surface-muted))]">
                  <div
                    className={`h-full rounded-full ${critBar(row.key)}`}
                    style={{ width: `${data.counters.ci_total ? (row.count / data.counters.ci_total) * 100 : 0}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
          {primary && (
            <p className={`mt-3 text-xs ${primary.headroom_w != null && primary.headroom_w < 0 ? "text-[rgb(var(--danger))]" : "text-muted"}`}>
              {t("dashboard.powerHeadroom")} · <span className="font-mono">{primary.code ?? primary.name}</span>
              {" · "}
              <span className="tabular-nums">{primary.headroom_w ?? "—"}</span> Вт
            </p>
          )}
        </Panel>

        <Panel
          title={t("dashboard.mapTitle")}
          actions={
            powerDiagram ? (
              <Link to={`/diagrams/${powerDiagram.id}`} className="text-xs text-accent">
                {t("dashboard.openMap")}
              </Link>
            ) : (
              <Link to="/power" className="text-xs text-accent">
                {t("dashboard.openPower")}
              </Link>
            )
          }
        >
          {chain.length === 0 ? (
            <EmptyState title={t("dashboard.noPower")} action={<Link to="/power" className="text-sm text-accent">{t("dashboard.openPower")}</Link>} />
          ) : (
            <ol>
              {chain.map((node, index) => (
                <li key={node.id}>
                  {index > 0 && <div className="ml-[11px] h-2.5 w-px bg-[rgb(var(--border))]" />}
                  <Link
                    to={`/ci/${node.id}`}
                    className="flex items-center gap-2 rounded-md px-1 py-1 hover:bg-[rgb(var(--surface-muted))]"
                  >
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        node.headroom_w != null && node.headroom_w < 0
                          ? "bg-[rgb(var(--danger))]"
                          : node.warnings.length > 0
                            ? "bg-[rgb(var(--warn))]"
                            : "bg-[rgb(var(--ok))]"
                      }`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-xs">{node.code ?? node.name}</span>
                      <span className="block truncate text-[11px] text-muted">
                        {te("powerNodeType", node.node_type)}
                        {node.name !== (node.code ?? node.name) ? ` · ${node.name}` : ""}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <Panel title={t("dashboard.activity")} bodyClassName="p-0">
          {feed.length === 0 ? (
            <EmptyState title={t("app.empty")} />
          ) : (
            <ul>
              {feed.map((item) => {
                const href = item.entity_type === "CI" && item.entity_id ? `/ci/${item.entity_id}` : null;
                const body = (
                  <>
                    <span className="block truncate text-sm">{item.entity_label ?? te("entityType", item.entity_type)}</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {te("auditAction", item.action)}
                      {item.actor_label ? ` · ${item.actor_label}` : ""}
                      {" · "}
                      {formatRelative(item.occurred_at, locale)}
                    </span>
                  </>
                );
                return (
                  <li key={item.id} className="border-b border-app last:border-0">
                    {href ? (
                      <Link to={href} className="block px-4 py-2.5 hover:bg-[rgb(var(--surface-muted))]">
                        {body}
                      </Link>
                    ) : (
                      <div className="px-4 py-2.5">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_18rem]">
        <Panel title={t("dashboard.dataQuality")}>
          <div className="mb-3">
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-muted">{t("dashboard.provenanceCoverage")}</span>
              <span className="text-sm font-semibold tabular-nums">{Math.round(coverage)}%</span>
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[rgb(var(--surface-muted))]">
              <div className="h-full rounded-full bg-[rgb(var(--accent))]" style={{ width: `${Math.min(coverage, 100)}%` }} />
            </div>
          </div>
          <ul className="grid gap-2 sm:grid-cols-2">
            {[
              [t("dashboard.withoutOwner"), quality.ci_without_owner, "/ci?missing=owner"],
              [t("dashboard.withoutLocation"), quality.ci_without_location, "/ci?missing=location"],
              [t("dashboard.documentsReview"), data.counters.documents_review_due, "/documents"],
              [t("dashboard.ciCritical"), data.counters.ci_critical, "/ci?criticality=CRITICAL"],
            ].map(([label, value, href]) => (
              <li key={String(label)}>
                <Link
                  to={String(href)}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-[rgb(var(--surface-muted))]"
                >
                  <span className="text-sm">{label}</span>
                  <span className="text-sm font-semibold tabular-nums">{value}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title={t("dashboard.quick")}>
          <ul className="flex flex-col gap-1">
            {[
              ["/work", t("dashboard.openTasks")],
              ["/projects", t("nav.projects")],
              ["/ci", t("dashboard.openObjects")],
              ["/diagrams", t("nav.diagrams")],
              ["/power", t("nav.power")],
            ].map(([to, label]) => (
              <li key={to}>
                <Link to={to} className="block rounded-md px-2 py-1.5 text-sm hover:bg-[rgb(var(--surface-muted))]">
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
