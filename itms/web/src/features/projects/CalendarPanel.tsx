import { useState } from "react";

import { useI18n } from "@/i18n";
import type { ProjectView } from "@/shared/api/types";

function monthStart(anchor: Date) {
  return new Date(anchor.getFullYear(), anchor.getMonth(), 1);
}

function iso(date: Date) {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function CalendarPanel({
  view,
  onOpen,
  onMove,
}: {
  view: ProjectView;
  onOpen: (taskId: string) => void;
  onMove: (taskId: string, due: string) => void;
}) {
  const { t } = useI18n();
  const [cursor, setCursor] = useState(() => monthStart(new Date()));
  const first = monthStart(cursor);
  const start = new Date(first);
  start.setDate(1 - ((first.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
  const title = first.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });

  return (
    <div data-testid="project-calendar">
      <div className="mb-3 flex items-center justify-between">
        <button type="button" className="text-sm text-muted" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>
          {t("projects.prevMonth")}
        </button>
        <h3 className="text-sm font-medium capitalize">{title}</h3>
        <button type="button" className="text-sm text-muted" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>
          {t("projects.nextMonth")}
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-xs">
        {days.map((date) => {
          const key = iso(date);
          const inMonth = date.getMonth() === first.getMonth();
          const tasks = view.tasks.filter((task) => task.due_date === key && !task.parent_id);
          const milestones = view.milestones.filter((item) => item.due_date === key);
          return (
            <div
              key={key}
              className={
                inMonth
                  ? "min-h-24 rounded border border-app p-1"
                  : "min-h-24 rounded border border-transparent p-1 opacity-40"
              }
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                const taskId = event.dataTransfer.getData("text/plain");
                if (taskId) onMove(taskId, key);
              }}
            >
              <div className="text-muted">{date.getDate()}</div>
              {milestones.map((item) => (
                <p key={item.id} className="truncate text-[rgb(var(--accent))]">
                  {item.name}
                </p>
              ))}
              {tasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  draggable
                  onDragStart={(event) => event.dataTransfer.setData("text/plain", task.id)}
                  className="mt-0.5 block w-full truncate rounded bg-[rgb(var(--surface-muted))] px-1 text-left"
                  onClick={() => onOpen(task.id)}
                >
                  {task.label} {task.title}
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
