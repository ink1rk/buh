import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/shared/lib/cn";

import { IconButton } from "./Button";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: "sm" | "md" | "lg";
}

const WIDTHS = { sm: "max-w-md", md: "max-w-2xl", lg: "max-w-4xl" } as const;

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "md",
}: DialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 p-4 pt-[8vh]">
      <button
        type="button"
        aria-label="Закрыть"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "surface animate-in relative w-full rounded-lg shadow-2xl",
          WIDTHS[width],
        )}
      >
        <header className="flex items-start justify-between gap-3 border-b border-app px-4 py-2.5">
          <div>
            <h2 className="text-sm font-semibold">{title}</h2>
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          <IconButton label="Закрыть" onClick={onClose}>
            <X size={15} />
          </IconButton>
        </header>
        <div className="max-h-[65vh] overflow-y-auto px-4 py-3">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-app px-4 py-2.5">{footer}</footer>
        )}
      </div>
    </div>,
    document.body,
  );
}
