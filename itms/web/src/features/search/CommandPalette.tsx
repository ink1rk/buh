import { Boxes, CornerDownLeft, Cpu, FileText, FolderKanban, ListChecks, MapPin, Search, Users, Workflow, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useSearch } from "@/shared/api/queries";
import type { SearchHit } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { cn } from "@/shared/lib/cn";
import { useUiStore } from "@/shared/store/ui";
import { Spinner } from "@/shared/ui/Layout";

const ENTITY_ICON: Record<string, ComponentType<{ size?: number }>> = {
  CI: Boxes,
  LOCATION: MapPin,
  DOCUMENT: FileText,
  EMPLOYEE: Users,
};

function pathFor(hit: SearchHit): string | null {
  switch (hit.entity_type) {
    case "CI":
      return `/ci/${hit.entity_id}`;
    case "DOCUMENT":
      return `/documents/${hit.entity_id}`;
    case "LOCATION":
      return `/locations?location=${hit.entity_id}`;
    case "EMPLOYEE":
      return `/directory?employee=${hit.entity_id}`;
    default:
      return null;
  }
}

export function CommandPalette() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const open = useUiStore((state) => state.paletteOpen);
  const setOpen = useUiStore((state) => state.setPaletteOpen);
  const recent = useUiStore((state) => state.recent);
  const pushRecent = useUiStore((state) => state.pushRecent);

  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounced = useDebounced(query, 220);
  const { data, isFetching } = useSearch(debounced, open);

  const hits = useMemo(() => data?.hits ?? [], [data]);
  const actions = useMemo(
    () => [
      { label: t("search.actionTask"), path: "/work", icon: ListChecks },
      { label: t("search.actionProject"), path: "/projects", icon: FolderKanban },
      { label: t("search.actionObject"), path: "/ci", icon: Boxes },
      { label: t("search.actionDiagram"), path: "/diagrams", icon: Workflow },
      { label: t("search.actionPower"), path: "/power", icon: Zap },
      { label: t("search.actionVirtualization"), path: "/virtualization", icon: Cpu },
    ],
    [t],
  );

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const timer = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => setCursor(0), [debounced]);

  if (!open) return null;

  const go = (hit: SearchHit) => {
    const path = pathFor(hit);
    if (!path) return;
    pushRecent({ id: hit.entity_id, title: hit.title, path });
    setOpen(false);
    navigate(path);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") return setOpen(false);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((value) => Math.min(value + 1, Math.max(hits.length - 1, 0)));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((value) => Math.max(value - 1, 0));
    }
    if (event.key === "Enter" && hits[cursor]) go(hits[cursor]);
  };

  const showRecent = !debounced.trim() && recent.length > 0;

  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-[rgb(8_9_11/0.55)] p-4 pt-[14vh] backdrop-blur-sm">
      <button
        type="button"
        aria-label={t("app.close")}
        className="absolute inset-0 cursor-default"
        onClick={() => setOpen(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("nav.commandPalette")}
        className="surface shadow-pop animate-in relative w-full max-w-2xl overflow-hidden rounded-2xl"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-2.5 border-b border-app px-4 py-3.5">
          <Search size={15} className="text-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("search.placeholder")}
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-[rgb(var(--text-muted))]"
          />
          {isFetching && <Spinner />}
        </div>

        <div className="max-h-[52vh] overflow-y-auto">
          {!debounced.trim() && (
            <ul className="py-1">
              <li className="px-4 py-1 text-[0.7rem] font-medium tracking-wide text-muted uppercase">
                {t("search.actions")}
              </li>
              {actions.map((action) => {
                const Icon = action.icon;
                return (
                  <li key={action.path}>
                    <button
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        navigate(action.path);
                      }}
                      className="flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm hover:bg-[rgb(var(--surface-muted))]"
                    >
                      <Icon size={15} />
                      <span>{action.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {showRecent && (
            <ul className="py-1">
              <li className="px-3 py-1 text-[0.7rem] font-medium tracking-wide text-muted uppercase">
                {t("search.recent")}
              </li>
              {recent.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      navigate(item.path);
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm hover:bg-[rgb(var(--surface-muted))]"
                  >
                    <span className="truncate">{item.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!showRecent && debounced.trim() && !hits.length && !isFetching && (
            <p className="px-3 py-8 text-center text-sm text-muted">{t("search.nothing")}</p>
          )}

          {hits.length > 0 && (
            <ul className="py-1">
              {hits.map((hit, index) => {
                const Icon = ENTITY_ICON[hit.entity_type] ?? Boxes;
                return (
                  <li key={`${hit.entity_type}-${hit.entity_id}`}>
                    <button
                      type="button"
                      onMouseEnter={() => setCursor(index)}
                      onClick={() => go(hit)}
                      className={cn(
                        "flex w-full items-center gap-2.5 px-4 py-2 text-left",
                        index === cursor && "bg-[rgb(var(--accent-soft))]",
                      )}
                    >
                      <Icon size={15} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm">{hit.title}</span>
                        {hit.subtitle && (
                          <span className="block truncate text-xs text-muted">{hit.subtitle}</span>
                        )}
                      </span>
                      <span className="shrink-0 text-[0.7rem] text-muted">
                        {te("entityType", hit.entity_type)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

        </div>

        <footer className="flex items-center gap-3 border-t border-app px-3 py-1.5 text-[0.7rem] text-muted">
          <span className="inline-flex items-center gap-1">
            <CornerDownLeft size={11} /> {t("search.open")}
          </span>
          <span>↑ ↓ {t("search.navigate")}</span>
          <span className="ml-auto">Esc — {t("app.close")}</span>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
