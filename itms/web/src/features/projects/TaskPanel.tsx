import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useEmployees, useTaskWork } from "@/shared/api/queries";
import type { ProjectView } from "@/shared/api/types";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Input, Select, Textarea } from "@/shared/ui/Field";
import { toast } from "@/shared/ui/toast";

const TASK_NEXT: Record<string, string[]> = {
  NEW: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["ON_HOLD", "BLOCKED", "REVIEW", "DONE", "CANCELLED"],
  ON_HOLD: ["IN_PROGRESS", "CANCELLED"],
  BLOCKED: ["IN_PROGRESS", "CANCELLED"],
  REVIEW: ["DONE", "IN_PROGRESS", "CANCELLED"],
  DONE: [],
  CANCELLED: [],
};

function optionsOf(current: string, next: string[], label: (value: string) => string) {
  return [current, ...next.filter((item) => item !== current)].map((value) => ({
    value,
    label: label(value),
  }));
}

export function waitingOn(taskId: string, view: ProjectView) {
  return view.dependencies
    .filter((dep) => dep.successor_id === taskId && dep.dep_kind === "FS")
    .map((dep) => view.tasks.find((task) => task.id === dep.predecessor_id))
    .filter((task) => task && task.status !== "DONE" && task.status !== "CANCELLED");
}

export function TaskPanel({
  projectId,
  taskId,
  view,
  onClose,
}: {
  projectId: string;
  taskId: string;
  view: ProjectView;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const task = view.tasks.find((item) => item.id === taskId);
  const { data: employees } = useEmployees();
  const { data: work } = useTaskWork(projectId, taskId);
  const [comment, setComment] = useState("");
  const [check, setCheck] = useState("");
  const [subtask, setSubtask] = useState("");
  const invalidate = [keys.project(projectId), keys.projects, keys.inbox, keys.taskWork(projectId, taskId)];
  const write = useApiMutation((run: () => Promise<unknown>) => run(), invalidate, {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err) => toast.error(describeError(err, t)),
  });

  if (!task) return null;
  const children = view.tasks.filter((item) => item.parent_id === task.id);
  const doneChildren = children.filter((item) => item.status === "DONE").length;
  const blocked = waitingOn(task.id, view);
  const checks = work?.checks ?? [];
  const doneChecks = checks.filter((item) => item.done).length;

  return (
    <Dialog open title={task.title} width="lg" onClose={onClose}>
      <div className="flex flex-col gap-4" data-testid="task-panel">
        <p className="font-mono text-xs text-muted">{task.label}</p>
        {blocked.length > 0 && (
          <p className="text-sm text-[rgb(var(--danger))]">
            {t("projects.waiting")}{" "}
            {blocked.map((item) => item?.label).filter(Boolean).join(", ")}
          </p>
        )}
        <div className="grid gap-2 sm:grid-cols-2">
          <Select
            aria-label={t("projects.status")}
            value={task.status}
            options={optionsOf(task.status, TASK_NEXT[task.status] ?? [], (value) =>
              te("taskStatus", value),
            )}
            onChange={(event) =>
              write.mutate(() => mutations.updateTask(projectId, task.id, { status: event.target.value }))
            }
          />
          <Select
            aria-label={t("projects.priority")}
            value={task.priority}
            options={["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => ({
              value,
              label: te("priority", value),
            }))}
            onChange={(event) =>
              write.mutate(() =>
                mutations.updateTask(projectId, task.id, { priority: event.target.value }),
              )
            }
          />
          <Select
            aria-label={t("projects.assignee")}
            value={task.assignee_id ?? ""}
            placeholder={t("projects.assignee")}
            options={(employees ?? []).map((item) => ({ value: item.id, label: item.full_name }))}
            onChange={(event) =>
              write.mutate(() =>
                mutations.updateTask(projectId, task.id, { assignee_id: event.target.value || null }),
              )
            }
          />
          <Input
            aria-label={t("projects.due")}
            type="date"
            value={task.due_date ?? ""}
            onChange={(event) =>
              write.mutate(() =>
                mutations.updateTask(projectId, task.id, { due_date: event.target.value || null }),
              )
            }
          />
        </div>
        <Textarea
          aria-label={t("projects.description")}
          defaultValue={task.description}
          key={task.description}
          rows={3}
          onBlur={(event) => {
            if (event.target.value === task.description) return;
            write.mutate(() =>
              mutations.updateTask(projectId, task.id, { description: event.target.value }),
            );
          }}
        />
        <section>
          <h3 className="mb-2 text-xs font-medium text-muted">
            {t("projects.checklist")} {checks.length > 0 ? `${doneChecks}/${checks.length}` : ""}
          </h3>
          <ul className="mb-2 flex flex-col gap-1">
            {checks.map((item) => (
              <li key={item.id}>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={item.done}
                    onChange={(event) =>
                      write.mutate(() =>
                        mutations.updateCheck(projectId, task.id, item.id, event.target.checked),
                      )
                    }
                  />
                  <span className={item.done ? "text-muted line-through" : ""}>{item.title}</span>
                </label>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Input
              value={check}
              placeholder={t("projects.addCheck")}
              onChange={(event) => setCheck(event.target.value)}
            />
            <Button
              data-testid="add-check"
              disabled={!check.trim() || write.isPending}
              onClick={() => {
                const title = check.trim();
                setCheck("");
                write.mutate(() => mutations.addCheck(projectId, task.id, title));
              }}
            >
              {t("app.create")}
            </Button>
          </div>
        </section>
        <section>
          <h3 className="mb-2 text-xs font-medium text-muted">
            {t("projects.subtasks")} {children.length > 0 ? `${doneChildren}/${children.length}` : ""}
          </h3>
          <ul className="mb-2 flex flex-col gap-1 text-sm">
            {children.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2">
                <span>
                  <span className="mr-2 font-mono text-xs text-muted">{item.label}</span>
                  {item.title}
                </span>
                <Badge tone={item.status === "DONE" ? "ok" : "neutral"}>
                  {te("taskStatus", item.status)}
                </Badge>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Input
              value={subtask}
              placeholder={t("projects.addSubtask")}
              onChange={(event) => setSubtask(event.target.value)}
            />
            <Button
              disabled={!subtask.trim() || write.isPending}
              onClick={() => {
                const title = subtask.trim();
                setSubtask("");
                write.mutate(() =>
                  mutations.addTask(projectId, {
                    title,
                    parent_id: task.id,
                    task_type: "SUBTASK",
                  }),
                );
              }}
            >
              {t("app.create")}
            </Button>
          </div>
        </section>
        <section>
          <h3 className="mb-2 text-xs font-medium text-muted">{t("projects.comments")}</h3>
          <ul className="mb-2 flex flex-col gap-2">
            {(work?.comments ?? []).map((item) => (
              <li key={item.id} className="rounded-md border border-app px-2 py-1.5 text-sm">
                <p>{item.body}</p>
                <p className="text-xs text-muted">{item.author_label}</p>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Input
              data-testid="comment-body"
              value={comment}
              placeholder={t("projects.addComment")}
              onChange={(event) => setComment(event.target.value)}
            />
            <Button
              data-testid="add-comment"
              variant="primary"
              disabled={!comment.trim() || write.isPending}
              onClick={() => {
                const body = comment.trim();
                setComment("");
                write.mutate(() => mutations.addComment(projectId, task.id, body));
              }}
            >
              {t("app.create")}
            </Button>
          </div>
        </section>
      </div>
    </Dialog>
  );
}
