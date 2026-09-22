import type { ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-[rgb(var(--surface-muted))] text-muted border-app",
  accent: "bg-[rgb(var(--accent-soft))] text-[rgb(var(--accent))] border-transparent",
  ok: "bg-[rgb(var(--ok)/0.14)] text-[rgb(var(--ok))] border-transparent",
  warn: "bg-[rgb(var(--warn)/0.16)] text-[rgb(var(--warn))] border-transparent",
  danger: "bg-[rgb(var(--danger)/0.14)] text-[rgb(var(--danger))] border-transparent",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const CI_STATUS_TONE: Record<string, Tone> = {
  PLANNED: "neutral",
  ORDERED: "neutral",
  IN_STOCK: "neutral",
  ACTIVE: "ok",
  DEGRADED: "warn",
  MAINTENANCE: "warn",
  RESERVED: "accent",
  DECOMMISSIONING: "warn",
  RETIRED: "danger",
};

const CRITICALITY_TONE: Record<string, Tone> = {
  LOW: "neutral",
  MEDIUM: "accent",
  HIGH: "warn",
  CRITICAL: "danger",
};

const DOCUMENT_STATUS_TONE: Record<string, Tone> = {
  DRAFT: "neutral",
  IN_REVIEW: "warn",
  APPROVED: "ok",
  OBSOLETE: "danger",
  ARCHIVED: "neutral",
};

const EMPLOYEE_STATUS_TONE: Record<string, Tone> = {
  ACTIVE: "ok",
  VACATION: "accent",
  SICK_LEAVE: "warn",
  DISMISSED: "neutral",
};

const AUDIT_ACTION_TONE: Record<string, Tone> = {
  CREATE: "ok",
  UPDATE: "accent",
  DELETE: "danger",
  ARCHIVE: "warn",
  RESTORE: "ok",
  STATUS: "accent",
  LOGIN_FAILED: "danger",
};

export const TONE_MAPS = {
  ciStatus: CI_STATUS_TONE,
  criticality: CRITICALITY_TONE,
  documentStatus: DOCUMENT_STATUS_TONE,
  employeeStatus: EMPLOYEE_STATUS_TONE,
  auditAction: AUDIT_ACTION_TONE,
} as const;

export function toneFor(map: keyof typeof TONE_MAPS, value: string | null | undefined): Tone {
  if (!value) return "neutral";
  return TONE_MAPS[map][value] ?? "neutral";
}
