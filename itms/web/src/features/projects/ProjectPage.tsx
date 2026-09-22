import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useCiList,
  useEmployees,
  useProject,
} from "@/shared/api/queries";
import type { ProjectView, ScheduleItem } from "@/shared/api/types";
import { CalendarPanel } from "@/features/projects/CalendarPanel";
import { TaskPanel, waitingOn } from "@/features/projects/TaskPanel";
import { TransitionPanel } from "@/features/projects/TransitionPanel";
import { Badge, type Tone } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { PageHeader, Panel } from "@/shared/ui/Layout";
import { Tabs } from "@/shared/ui/Tabs";
import { toast } from "@/shared/ui/toast";

const PROJECT_NEXT: Record<string, string[]> = {
  DRAFT: ["PLANNING", "CANCELLED"],
  PLANNING: ["IN_PROGRESS", "ON_HOLD", "CANCELLED"],
  IN_PROGRESS: ["ON_HOLD", "COMPLETED", "CANCELLED"],
  ON_HOLD: ["IN_PROGRESS", "CANCELLED"],
  COMPLETED: [],
  CANCELLED: [],
};

const TASK_NEXT: Record<string, string[]> = {
  NEW: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["ON_HOLD", "BLOCKED", "REVIEW", "DONE", "CANCELLED"],
  ON_HOLD: ["IN_PROGRESS", "CANCELLED"],
  BLOCKED: ["IN_PROGRESS", "CANCELLED"],
  REVIEW: ["DONE", "IN_PROGRESS", "CANCELLED"],
  DONE: [],
  CANCELLED: [],
};

const BOARD = ["NEW", "IN_PROGRESS", "BLOCKED", "REVIEW", "DONE"] as const;

function healthTone(status: string): Tone {
  if (status === "DELAYED") return "danger";
  if (status === "AT_RISK") return "warn";
  if (status === "ON_TRACK") return "ok";
  return "neutral";
}

function optionsOf(current: string, next: string[], label: (value: string) => string) {
  return [current, ...next.filter((item) => item !== current)].map((value) => ({
    value,
    label: label(value),
  }));
}

export function ProjectPage() {
  const { projectId } = useParams();
  const { t, te } = useI18n();
  const { data, isLoading } = useProject(projectId);
  const [params] = useSearchParams();
  const taskFromUrl = params.get("task");
  const [tab, setTab] = useState("overview");
  const [openTask, setOpenTask] = useState<string | null>(taskFromUrl);
  useEffect(() => {
    if (taskFromUrl) setOpenTask(taskFromUrl);
  }, [taskFromUrl]);
  const moveDue = useProjectWrite(projectId ?? "");

  if (isLoading || !data || !projectId) {
    return <p className="text-sm text-muted">{t("app.loading")}</p>;
  }

  const project = data.project;
  return (
    <div data-testid="project-page">
      <PageHeader
        title={project.name}
        subtitle={project.key}
        actions={
          <span data-testid="project-health">
            <Badge tone={healthTone(data.health.status)}>{te("health", data.health.status)}</Badge>
          </span>
        }
      />
      <div className="mb-4 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded bg-[rgb(var(--surface-muted))]">
          <div
            className="h-full bg-[rgb(var(--accent))]"
            style={{ width: `${Math.min(100, project.progress_pct)}%` }}
          />
        </div>
        <span className="tabular-nums text-xs text-muted">{project.progress_pct}%</span>
      </div>
      <Tabs
        className="mb-4"
        active={tab}
        onChange={setTab}
        items={[
          { id: "overview", label: t("projects.overview") },
          { id: "tasks", label: t("projects.tasks"), badge: data.tasks.length },
          { id: "board", label: t("projects.board") },
          { id: "schedule", label: t("projects.schedule") },
          { id: "calendar", label: t("projects.calendar") },
          { id: "infra", label: t("projects.infrastructure"), badge: data.cis.length },
          { id: "transition", label: t("projects.transition") },
        ]}
      />
      {tab === "overview" && <Overview projectId={projectId} view={data} />}
      {tab === "tasks" && <Tasks projectId={projectId} view={data} onOpen={setOpenTask} />}
      {tab === "board" && <Board projectId={projectId} view={data} onOpen={setOpenTask} />}
      {tab === "schedule" && <Schedule view={data} />}
      {tab === "calendar" && (
        <CalendarPanel
          view={data}
          onOpen={setOpenTask}
          onMove={(taskId, due) =>
            moveDue.mutate(() => mutations.updateTask(projectId, taskId, { due_date: due }))
          }
        />
      )}
      {tab === "infra" && <Infrastructure projectId={projectId} view={data} />}
      {tab === "transition" && <TransitionPanel projectId={projectId} />}
      {openTask && (
        <TaskPanel
          projectId={projectId}
          taskId={openTask}
          view={data}
          onClose={() => setOpenTask(null)}
        />
      )}
    </div>
  );
}

function useProjectWrite(projectId: string) {
  const { t } = useI18n();
  return useApiMutation(
    (run: () => Promise<ProjectView>) => run(),
    [keys.projects, keys.project(projectId)],
    {
      onSuccess: () => toast.success(t("app.saved")),
      onError: (err) => toast.error(describeError(err, t)),
    },
  );
}

function Overview({ projectId, view }: { projectId: string; view: ProjectView }) {
  const { t, te } = useI18n();
  const { data: employees } = useEmployees();
  const write = useProjectWrite(projectId);
  const project = view.project;
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  const [status, setStatus] = useState(project.status);
  const [priority, setPriority] = useState(project.priority);
  const [ownerId, setOwnerId] = useState(project.owner_id ?? "");
  const [start, setStart] = useState(project.start_date ?? "");
  const [due, setDue] = useState(project.due_date ?? "");
  const [budgetPlan, setBudgetPlan] = useState(
    project.budget_planned == null ? "" : String(project.budget_planned),
  );
  const [budgetFact, setBudgetFact] = useState(
    project.budget_actual == null ? "" : String(project.budget_actual),
  );
  const [phaseName, setPhaseName] = useState("");
  const [milestoneName, setMilestoneName] = useState("");
  const [milestoneDue, setMilestoneDue] = useState("");
  const [memberId, setMemberId] = useState("");
  const [memberRole, setMemberRole] = useState("участник");

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.8fr)]">
      <div className="flex flex-col gap-4">
        <Panel title={t("projects.overview")}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("projects.name")} htmlFor="passport-name" className="sm:col-span-2">
              <Input id="passport-name" value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label={t("projects.description")} htmlFor="passport-description" className="sm:col-span-2">
              <Textarea
                id="passport-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
            <Field label={t("projects.status")} htmlFor="passport-status">
              <Select
                id="passport-status"
                value={status}
                options={optionsOf(project.status, PROJECT_NEXT[project.status] ?? [], (value) =>
                  te("projectStatus", value),
                )}
                onChange={(event) => setStatus(event.target.value)}
              />
            </Field>
            <Field label={t("projects.priority")} htmlFor="passport-priority">
              <Select
                id="passport-priority"
                value={priority}
                options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => ({
                  value,
                  label: te("priority", value),
                }))}
                onChange={(event) => setPriority(event.target.value)}
              />
            </Field>
            <Field label={t("projects.owner")} htmlFor="passport-owner">
              <Select
                id="passport-owner"
                value={ownerId}
                placeholder="—"
                options={(employees ?? []).map((item) => ({ value: item.id, label: item.full_name }))}
                onChange={(event) => setOwnerId(event.target.value)}
              />
            </Field>
            <Field label={t("projects.start")} htmlFor="passport-start">
              <Input id="passport-start" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
            </Field>
            <Field label={t("projects.due")} htmlFor="passport-due">
              <Input id="passport-due" type="date" value={due} onChange={(event) => setDue(event.target.value)} />
            </Field>
            <Field label={t("projects.budgetPlan")} htmlFor="passport-plan">
              <Input id="passport-plan" value={budgetPlan} onChange={(event) => setBudgetPlan(event.target.value)} />
            </Field>
            <Field label={t("projects.budgetFact")} htmlFor="passport-fact">
              <Input id="passport-fact" value={budgetFact} onChange={(event) => setBudgetFact(event.target.value)} />
            </Field>
          </div>
          <div className="mt-3">
            <Button
              variant="primary"
              disabled={write.isPending || !name.trim()}
              onClick={() =>
                write.mutate(() =>
                  mutations.updateProject(projectId, {
                    name: name.trim(),
                    description,
                    status,
                    priority,
                    owner_id: ownerId || null,
                    start_date: start || null,
                    due_date: due || null,
                    budget_planned: budgetPlan === "" ? null : Number(budgetPlan),
                    budget_actual: budgetFact === "" ? null : Number(budgetFact),
                  }),
                )
              }
            >
              {t("projects.savePassport")}
            </Button>
          </div>
        </Panel>
        <Panel title={t("projects.phases")}>
          <ul className="mb-3 flex flex-col gap-1">
            {view.phases.map((phase) => (
              <li key={phase.id} className="flex items-center justify-between gap-3 text-sm">
                <span>
                  {phase.order_index}. {phase.name}
                </span>
                <span className="tabular-nums text-muted">{phase.progress_pct}%</span>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Input
              value={phaseName}
              placeholder={t("projects.addPhase")}
              onChange={(event) => setPhaseName(event.target.value)}
            />
            <Button
              disabled={!phaseName.trim() || write.isPending}
              onClick={() => {
                const title = phaseName.trim();
                setPhaseName("");
                write.mutate(() => mutations.addPhase(projectId, { name: title }));
              }}
            >
              {t("app.create")}
            </Button>
          </div>
        </Panel>
      </div>
      <div className="flex flex-col gap-4">
        <Panel title={t("projects.health")}>
          {view.health.findings.length === 0 ? (
            <p className="text-sm text-muted">{t("projects.noFindings")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {view.health.findings.map((finding) => (
                <li key={finding.rule} className="text-sm">
                  <Badge tone={healthTone(finding.level)}>{te("health", finding.level)}</Badge>
                  <p className="mt-1">{finding.message}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={t("projects.milestones")}>
          <ul className="mb-3 flex flex-col gap-1 text-sm">
            {view.milestones.map((milestone) => (
              <li key={milestone.id} className="flex items-center justify-between gap-2">
                <span>{milestone.name}</span>
                <span className="text-muted">{milestone.due_date ?? "—"}</span>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2">
            <Input
              value={milestoneName}
              placeholder={t("projects.addMilestone")}
              onChange={(event) => setMilestoneName(event.target.value)}
            />
            <Input type="date" value={milestoneDue} onChange={(event) => setMilestoneDue(event.target.value)} />
            <Button
              disabled={!milestoneName.trim() || write.isPending}
              onClick={() => {
                const title = milestoneName.trim();
                setMilestoneName("");
                write.mutate(() =>
                  mutations.addMilestone(projectId, {
                    name: title,
                    due_date: milestoneDue || null,
                  }),
                );
              }}
            >
              {t("app.create")}
            </Button>
          </div>
        </Panel>
        <Panel title={t("projects.members")}>
          <ul className="mb-3 flex flex-col gap-1 text-sm">
            {view.members.map((member) => (
              <li key={member.employee_id}>
                {member.full_name}
                <span className="ml-2 text-muted">{member.role}</span>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2">
            <Select
              value={memberId}
              placeholder={t("projects.addMember")}
              options={(employees ?? []).map((item) => ({ value: item.id, label: item.full_name }))}
              onChange={(event) => setMemberId(event.target.value)}
            />
            <Input value={memberRole} onChange={(event) => setMemberRole(event.target.value)} />
            <Button
              disabled={!memberId || write.isPending}
              onClick={() =>
                write.mutate(() =>
                  mutations.addMember(projectId, { employee_id: memberId, role: memberRole.trim() || "участник" }),
                )
              }
            >
              {t("app.create")}
            </Button>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function RecurrenceForm({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [cadence, setCadence] = useState("weekly");
  const write = useApiMutation(
    (body: Record<string, unknown>) => mutations.addRecurrence(projectId, body),
    [keys.projects, keys.project(projectId)],
    {
      onSuccess: () => {
        setTitle("");
        toast.success(t("app.saved"));
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );
  return (
    <Panel title={t("projects.recurrence")}>
      <div className="flex flex-wrap gap-2">
        <Input
          className="min-w-48 flex-1"
          value={title}
          placeholder={t("projects.addTask")}
          onChange={(event) => setTitle(event.target.value)}
        />
        <Select
          value={cadence}
          options={[
            { value: "daily", label: t("projects.daily") },
            { value: "weekly", label: t("projects.weekly") },
            { value: "monthly", label: t("projects.monthly") },
          ]}
          onChange={(event) => setCadence(event.target.value)}
        />
        <Button
          data-testid="add-recurrence"
          variant="primary"
          disabled={!title.trim() || write.isPending}
          onClick={() =>
            write.mutate({
              title: title.trim(),
              cadence,
              weekday: cadence === "weekly" ? 0 : null,
            })
          }
        >
          {t("app.create")}
        </Button>
      </div>
    </Panel>
  );
}

function Tasks({
  projectId,
  view,
  onOpen,
}: {
  projectId: string;
  view: ProjectView;
  onOpen: (taskId: string) => void;
}) {
  const { t, te } = useI18n();
  const { data: employees } = useEmployees();
  const write = useProjectWrite(projectId);
  const [title, setTitle] = useState("");
  const [phaseId, setPhaseId] = useState("");
  const [estimate, setEstimate] = useState("");
  const [predecessor, setPredecessor] = useState("");
  const [successor, setSuccessor] = useState("");
  const [kind, setKind] = useState("FS");
  const [taskId, setTaskId] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [workDate, setWorkDate] = useState("");
  const [minutes, setMinutes] = useState("60");

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t("projects.tasks")}>
        <div className="mb-3 flex flex-wrap gap-2">
          <Input
            className="min-w-48 flex-1"
            value={title}
            placeholder={t("projects.addTask")}
            onChange={(event) => setTitle(event.target.value)}
          />
          <Select
            value={phaseId}
            placeholder={t("projects.phases")}
            options={view.phases.map((phase) => ({ value: phase.id, label: phase.name }))}
            onChange={(event) => setPhaseId(event.target.value)}
          />
          <Input
            className="w-28"
            value={estimate}
            placeholder={t("projects.estimate")}
            onChange={(event) => setEstimate(event.target.value)}
          />
          <Button
            variant="primary"
            disabled={!title.trim() || write.isPending}
            onClick={() => {
              const next = title.trim();
              setTitle("");
              write.mutate(() =>
                mutations.addTask(projectId, {
                  title: next,
                  phase_id: phaseId || null,
                  estimate_min: Number(estimate) || 0,
                }),
              );
            }}
          >
            {t("app.create")}
          </Button>
        </div>
        {view.tasks.length === 0 ? (
          <p className="text-sm text-muted">{t("projects.noTasks")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1 pr-2 font-medium">{t("projects.key")}</th>
                <th className="py-1 pr-2 font-medium">{t("projects.name")}</th>
                <th className="py-1 pr-2 font-medium">{t("projects.status")}</th>
                <th className="py-1 pr-2 font-medium">{t("projects.assignee")}</th>
                <th className="py-1 font-medium">{t("projects.progress")}</th>
              </tr>
            </thead>
            <tbody>
              {view.tasks.map((task) => (
                <tr
                  key={task.id}
                  className="cursor-pointer border-t border-app"
                  onClick={() => onOpen(task.id)}
                >
                  <td className="py-1.5 pr-2 font-mono text-xs">{task.label}</td>
                  <td className="py-1.5 pr-2">
                    {task.title}
                    {waitingOn(task.id, view).length > 0 && (
                      <span className="ml-2 text-xs text-[rgb(var(--danger))]">{t("projects.waiting")}</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2">
                    <div className="flex items-center gap-1">
                      <Select
                        value={task.status}
                        options={optionsOf(task.status, TASK_NEXT[task.status] ?? [], (value) =>
                          te("taskStatus", value),
                        )}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) => {
                          const next = event.currentTarget.value;
                          write.mutate(() =>
                            mutations.updateTask(projectId, task.id, { status: next }),
                          );
                        }}
                      />
                      {(TASK_NEXT[task.status] ?? [])[0] && (
                        <Button
                          size="sm"
                          data-testid={`advance-${task.label}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            const next = (TASK_NEXT[task.status] ?? [])[0];
                            if (!next) return;
                            write.mutate(() =>
                              mutations.updateTask(projectId, task.id, { status: next }),
                            );
                          }}
                        >
                          {te("taskStatus", (TASK_NEXT[task.status] ?? [])[0] ?? "")}
                        </Button>
                      )}
                    </div>
                  </td>
                  <td className="py-1.5 pr-2 text-muted">{task.assignee_name ?? "—"}</td>
                  <td className="py-1.5 tabular-nums">{task.progress_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <RecurrenceForm projectId={projectId} />
      <Panel title={t("projects.dependency")}>
        <div className="flex flex-wrap gap-2">
          <Select
            value={predecessor}
            placeholder={t("projects.predecessor")}
            options={view.tasks.map((task) => ({ value: task.id, label: `${task.label} ${task.title}` }))}
            onChange={(event) => setPredecessor(event.target.value)}
          />
          <Select
            value={successor}
            placeholder={t("projects.successor")}
            options={view.tasks.map((task) => ({ value: task.id, label: `${task.label} ${task.title}` }))}
            onChange={(event) => setSuccessor(event.target.value)}
          />
          <Select
            value={kind}
            options={["FS", "SS", "FF", "SF"].map((value) => ({ value, label: te("depKind", value) }))}
            onChange={(event) => setKind(event.target.value)}
          />
          <Button
            disabled={!predecessor || !successor || predecessor === successor || write.isPending}
            onClick={() =>
              write.mutate(() =>
                mutations.addDependency(projectId, {
                  predecessor_id: predecessor,
                  successor_id: successor,
                  dep_kind: kind,
                }),
              )
            }
          >
            {t("app.create")}
          </Button>
        </div>
        <ul className="mt-3 flex flex-col gap-1 text-sm text-muted">
          {view.dependencies.map((dep) => {
            const from = view.tasks.find((task) => task.id === dep.predecessor_id);
            const to = view.tasks.find((task) => task.id === dep.successor_id);
            return (
              <li key={dep.id}>
                {from?.label} {te("depKind", dep.dep_kind)} {to?.label}
                {dep.lag_days ? ` +${dep.lag_days}` : ""}
              </li>
            );
          })}
        </ul>
      </Panel>
      <Panel title={t("projects.logTime")}>
        <div className="flex flex-wrap gap-2">
          <Select
            value={taskId}
            placeholder={t("projects.tasks")}
            options={view.tasks.map((task) => ({ value: task.id, label: task.label }))}
            onChange={(event) => setTaskId(event.target.value)}
          />
          <Select
            value={employeeId}
            placeholder={t("projects.assignee")}
            options={(employees ?? []).map((item) => ({ value: item.id, label: item.full_name }))}
            onChange={(event) => setEmployeeId(event.target.value)}
          />
          <Input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} />
          <Input className="w-24" value={minutes} onChange={(event) => setMinutes(event.target.value)} />
          <Button
            disabled={!taskId || !employeeId || !workDate || write.isPending}
            onClick={() =>
              write.mutate(() =>
                mutations.addTime(projectId, taskId, {
                  employee_id: employeeId,
                  work_date: workDate,
                  minutes: Number(minutes) || 60,
                }),
              )
            }
          >
            {t("app.save")}
          </Button>
        </div>
      </Panel>
    </div>
  );
}

function Board({
  projectId,
  view,
  onOpen,
}: {
  projectId: string;
  view: ProjectView;
  onOpen: (taskId: string) => void;
}) {
  const { t, te } = useI18n();
  const write = useProjectWrite(projectId);

  function move(taskId: string, status: string) {
    const task = view.tasks.find((item) => item.id === taskId);
    if (!task || task.status === status) return;
    if (!(TASK_NEXT[task.status] ?? []).includes(status)) {
      toast.error(t("errors.invalid_status_transition"));
      return;
    }
    write.mutate(() => mutations.updateTask(projectId, taskId, { status }));
  }

  return (
    <div className="grid gap-3 md:grid-cols-5" data-testid="kanban">
      {BOARD.map((status) => (
        <section
          key={status}
          className="surface min-h-48 rounded-lg p-2"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            move(event.dataTransfer.getData("text/plain"), status);
          }}
        >
          <h3 className="mb-2 text-xs font-medium text-muted">{te("taskStatus", status)}</h3>
          <div className="flex flex-col gap-2">
            {view.tasks
              .filter((task) => task.status === status)
              .map((task) => (
                <article
                  key={task.id}
                  draggable
                  onDragStart={(event) => event.dataTransfer.setData("text/plain", task.id)}
                  onClick={() => onOpen(task.id)}
                  className="cursor-grab rounded-md border border-app bg-[rgb(var(--surface))] p-2 text-sm"
                >
                  <p className="font-mono text-[0.65rem] text-muted">{task.label}</p>
                  <p>{task.title}</p>
                  {waitingOn(task.id, view).length > 0 && (
                    <p className="text-xs text-[rgb(var(--danger))]">{t("projects.waiting")}</p>
                  )}
                </article>
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Schedule({ view }: { view: ProjectView }) {
  const { t } = useI18n();
  const length = Math.max(view.schedule.length_days, 1);
  return (
    <Panel title={t("projects.schedule")}>
      <p className="mb-3 text-xs text-muted">{t("projects.softShift")}</p>
      <div className="flex flex-col gap-2">
        {view.schedule.items.map((item) => (
          <ScheduleRow key={item.task_id} item={item} length={length} />
        ))}
      </div>
    </Panel>
  );
}

function ScheduleRow({ item, length }: { item: ScheduleItem; length: number }) {
  const { t } = useI18n();
  const left = (item.es / length) * 100;
  const width = Math.max((item.duration_days / length) * 100, 1.5);
  return (
    <div
      className="grid items-center gap-3 sm:grid-cols-[14rem_minmax(0,1fr)_7rem]"
      data-testid="schedule-item"
      data-critical={item.critical ? "true" : "false"}
    >
      <div className="min-w-0">
        <p className="truncate text-sm">
          <span className="mr-2 font-mono text-xs text-muted">{item.label}</span>
          {item.title}
        </p>
      </div>
      <div className="relative h-5 rounded bg-[rgb(var(--surface-muted))]">
        <div
          className={
            item.critical
              ? "absolute top-1 h-3 rounded bg-[rgb(var(--danger))]"
              : "absolute top-1 h-3 rounded bg-[rgb(var(--accent))]"
          }
          style={{ left: `${left}%`, width: `${width}%` }}
          title={`${item.start_date} — ${item.finish_date}`}
        />
      </div>
      <p className="text-xs text-muted">
        {item.critical ? t("projects.critical") : `${t("projects.float")} ${item.float_days}`}
      </p>
    </div>
  );
}

function Infrastructure({ projectId, view }: { projectId: string; view: ProjectView }) {
  const { t } = useI18n();
  const write = useProjectWrite(projectId);
  const [query, setQuery] = useState("");
  const [ciId, setCiId] = useState("");
  const [involvement, setInvolvement] = useState("затронут");
  const { data: found } = useCiList({ q: query, limit: 20, offset: 0 });

  return (
    <Panel title={t("projects.infrastructure")}>
      <ul className="mb-3 flex flex-col gap-1 text-sm">
        {view.cis.map((item) => (
          <li key={item.ci_id} className="flex items-center justify-between gap-3">
            <span>
              {item.name}
              {item.code && <span className="ml-2 font-mono text-xs text-muted">{item.code}</span>}
            </span>
            <span className="flex items-center gap-2 text-muted">
              {item.involvement}
              <Button onClick={() => write.mutate(() => mutations.unlinkProjectCi(projectId, item.ci_id))}>
                {t("app.delete")}
              </Button>
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Input
          value={query}
          placeholder={t("app.search")}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Select
          value={ciId}
          placeholder={t("projects.linkCi")}
          options={(found?.items ?? []).map((item) => ({
            value: item.id,
            label: item.code ? `${item.code} ${item.name}` : item.name,
          }))}
          onChange={(event) => setCiId(event.target.value)}
        />
        <Select
          value={involvement}
          options={["изменяется", "создаётся", "выводится", "затронут"].map((value) => ({
            value,
            label: value,
          }))}
          onChange={(event) => setInvolvement(event.target.value)}
        />
        <Button
          disabled={!ciId || write.isPending}
          onClick={() =>
            write.mutate(() =>
              mutations.linkProjectCi(projectId, { ci_id: ciId, involvement }),
            )
          }
        >
          {t("app.create")}
        </Button>
      </div>
    </Panel>
  );
}
