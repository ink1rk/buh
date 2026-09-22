import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { createPortal } from "react-dom";
import { create } from "zustand";

import { cn } from "@/shared/lib/cn";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: string;
  tone: ToastTone;
  message: string;
  detail?: string;
}

interface ToastState {
  items: ToastItem[];
  push: (toast: Omit<ToastItem, "id">) => void;
  dismiss: (id: string) => void;
}

const useToastStore = create<ToastState>((set) => ({
  items: [],
  push: (toast) => {
    const id = crypto.randomUUID();
    set((state) => ({ items: [...state.items, { ...toast, id }] }));
    setTimeout(() => set((state) => ({ items: state.items.filter((i) => i.id !== id) })), 6000);
  },
  dismiss: (id) => set((state) => ({ items: state.items.filter((item) => item.id !== id) })),
}));

export const toast = {
  success: (message: string, detail?: string) =>
    useToastStore.getState().push({ tone: "success", message, detail }),
  error: (message: string, detail?: string) =>
    useToastStore.getState().push({ tone: "error", message, detail }),
  info: (message: string, detail?: string) =>
    useToastStore.getState().push({ tone: "info", message, detail }),
};

const ICONS = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
} as const;

const TONE_CLASS: Record<ToastTone, string> = {
  success: "text-[rgb(var(--ok))]",
  error: "text-[rgb(var(--danger))]",
  info: "text-[rgb(var(--accent))]",
};

export function ToastViewport() {
  const items = useToastStore((state) => state.items);
  const dismiss = useToastStore((state) => state.dismiss);
  if (!items.length) return null;

  return createPortal(
    <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-80 flex-col gap-2">
      {items.map((item) => {
        const Icon = ICONS[item.tone];
        return (
          <div
            key={item.id}
            role="status"
            className="surface shadow-pop animate-in pointer-events-auto flex items-start gap-2.5 rounded-xl px-3.5 py-3"
          >
            <Icon size={15} className={cn("mt-0.5 shrink-0", TONE_CLASS[item.tone])} />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium">{item.message}</p>
              {item.detail && <p className="mt-0.5 text-xs break-words text-muted">{item.detail}</p>}
            </div>
            <button
              type="button"
              aria-label="Закрыть"
              onClick={() => dismiss(item.id)}
              className="text-muted hover:text-app"
            >
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
}
