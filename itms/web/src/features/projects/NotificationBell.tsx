import { Bell } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { keys, mutations, useApiMutation, useNotifications } from "@/shared/api/queries";
import { IconButton } from "@/shared/ui/Button";

const KIND: Record<string, TranslationKey> = {
  assigned: "notifications.assigned",
  status: "notifications.status",
  comment: "notifications.comment",
  mention: "notifications.mention",
};

export function NotificationBell() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data } = useNotifications();
  const [open, setOpen] = useState(false);
  const mark = useApiMutation((id: string) => mutations.readNotification(id), [keys.notifications]);
  const markAll = useApiMutation(() => mutations.readNotifications(), [keys.notifications]);
  const items = data?.items ?? [];
  const unread = data?.unread ?? 0;

  return (
    <div className="relative">
      <IconButton
        label={t("notifications.title")}
        data-testid="notification-bell"
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={15} />
      </IconButton>
      {unread > 0 && (
        <span
          data-testid="notification-count"
          className="pointer-events-none absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[rgb(var(--danger))] px-1 text-[0.65rem] text-white"
        >
          {unread}
        </span>
      )}
      {open && (
        <div
          data-testid="notification-panel"
          className="surface absolute top-9 right-0 z-40 w-80 overflow-hidden rounded-lg border border-app shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-app px-3 py-2">
            <p className="text-xs font-medium">{t("notifications.title")}</p>
            {unread > 0 && (
              <button
                type="button"
                className="text-xs text-muted hover:text-app"
                onClick={() => markAll.mutate()}
              >
                {t("notifications.readAll")}
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="px-3 py-4 text-sm text-muted">{t("notifications.empty")}</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    data-testid="notification-item"
                    className="flex w-full flex-col gap-0.5 px-3 py-2 text-left hover:bg-[rgb(var(--surface-muted))]"
                    onClick={() => {
                      if (!item.read_at) mark.mutate(item.id);
                      setOpen(false);
                      if (item.project_id) {
                        const task = item.task_id ? `?task=${item.task_id}` : "";
                        navigate(`/projects/${item.project_id}${task}`);
                      }
                    }}
                  >
                    <span className="text-[0.65rem] text-muted">
                      {t(KIND[item.kind] ?? "notifications.title")}
                    </span>
                    <span className={item.read_at ? "text-sm text-muted" : "text-sm"}>{item.title}</span>
                    {item.body && <span className="truncate text-xs text-muted">{item.body}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
