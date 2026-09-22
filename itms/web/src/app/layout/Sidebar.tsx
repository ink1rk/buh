import {
  Boxes,
  FileText,
  FolderKanban,
  History,
  BarChart3,
  LayoutDashboard,
  Layers,
  ListChecks,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Server,
  Settings,
  Upload,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { cn } from "@/shared/lib/cn";
import { useUiStore } from "@/shared/store/ui";
import { IconButton } from "@/shared/ui/Button";
import { Mark } from "@/shared/ui/Mark";

interface NavItem {
  to: string;
  labelKey: TranslationKey;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  match: (pathname: string) => boolean;
}

interface NavGroup {
  labelKey: TranslationKey;
  items: NavItem[];
}

function starts(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

const GROUPS: NavGroup[] = [
  {
    labelKey: "nav.groupOverview",
    items: [
      {
        to: "/dashboard",
        labelKey: "nav.dashboard",
        icon: LayoutDashboard,
        match: (pathname) => pathname === "/dashboard",
      },
      {
        to: "/work",
        labelKey: "nav.work",
        icon: ListChecks,
        match: (pathname) => pathname === "/work",
      },
    ],
  },
  {
    labelKey: "nav.groupWork",
    items: [
      {
        to: "/projects",
        labelKey: "nav.projects",
        icon: FolderKanban,
        match: (pathname) => starts(pathname, ["/projects"]),
      },
      {
        to: "/analytics",
        labelKey: "nav.analytics",
        icon: BarChart3,
        match: (pathname) => pathname === "/analytics",
      },
    ],
  },
  {
    labelKey: "nav.groupInfrastructure",
    items: [
      {
        to: "/infrastructure",
        labelKey: "nav.infrastructure",
        icon: Boxes,
        match: (pathname) => starts(pathname, ["/infrastructure", "/ci", "/devices", "/ipam"]),
      },
      {
        to: "/diagrams",
        labelKey: "nav.diagrams",
        icon: Workflow,
        match: (pathname) => starts(pathname, ["/diagrams"]),
      },
      {
        to: "/network",
        labelKey: "nav.network",
        icon: Network,
        match: (pathname) => pathname === "/network",
      },
      {
        to: "/datacenter",
        labelKey: "nav.datacenter",
        icon: Server,
        match: (pathname) => starts(pathname, ["/datacenter", "/racks", "/floorplans", "/locations"]),
      },
      {
        to: "/power",
        labelKey: "nav.power",
        icon: Zap,
        match: (pathname) => pathname === "/power",
      },
    ],
  },
  {
    labelKey: "nav.groupKnowledge",
    items: [
      {
        to: "/documents",
        labelKey: "nav.documents",
        icon: FileText,
        match: (pathname) => starts(pathname, ["/documents"]),
      },
      {
        to: "/directory",
        labelKey: "nav.team",
        icon: Users,
        match: (pathname) => pathname === "/directory",
      },
    ],
  },
];

const SYSTEM: NavGroup = {
  labelKey: "nav.groupSystem",
  items: [
    {
      to: "/audit",
      labelKey: "nav.audit",
      icon: History,
      match: (pathname) => pathname === "/audit",
    },
    {
      to: "/catalog",
      labelKey: "nav.catalog",
      icon: Layers,
      match: (pathname) => pathname === "/catalog",
    },
    {
      to: "/imports",
      labelKey: "nav.imports",
      icon: Upload,
      match: (pathname) => pathname === "/imports",
    },
    {
      to: "/settings",
      labelKey: "nav.settings",
      icon: Settings,
      match: (pathname) => pathname === "/settings",
    },
  ],
};

function NavSection({
  group,
  collapsed,
  divided,
}: {
  group: NavGroup;
  collapsed: boolean;
  divided?: boolean;
}) {
  const { t } = useI18n();
  const { pathname } = useLocation();
  return (
    <div className={cn("flex flex-col", divided && (collapsed ? "mt-2" : "mt-1"))}>
      {collapsed ? (
        divided && <div className="mx-auto mb-2 h-px w-4 bg-[rgb(var(--border))]" />
      ) : (
        <p className="px-2.5 pt-3 pb-1 text-[0.62rem] font-semibold tracking-[0.14em] text-muted uppercase">
          {t(group.labelKey)}
        </p>
      )}
      <ul className="flex flex-col gap-px">
        {group.items.map((item) => {
          const Icon = item.icon;
          const label = t(item.labelKey);
          const active = item.match(pathname);
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                title={label}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] transition-colors",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-[rgb(var(--accent-soft))] font-semibold text-[rgb(var(--accent))]"
                    : "text-muted hover:bg-[rgb(var(--surface-muted))] hover:text-app",
                )}
              >
                <Icon size={15} strokeWidth={1.75} />
                {!collapsed && <span className="truncate">{label}</span>}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Sidebar() {
  const { t } = useI18n();
  const collapsed = useUiStore((state) => state.navCollapsed);
  const toggleNav = useUiStore((state) => state.toggleNav);

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-app bg-[rgb(var(--sidebar))] py-3",
        collapsed ? "w-14 px-1.5" : "w-[15.25rem] px-2.5",
      )}
    >
      <div className={cn("flex items-center gap-2 px-1.5", collapsed && "flex-col px-0")}>
        <Mark size={26} />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <p className="text-sm leading-tight font-semibold tracking-tight">{t("app.name")}</p>
            <p className="truncate text-[0.65rem] leading-4 text-muted">{t("app.tagline")}</p>
          </div>
        )}
        <IconButton label={collapsed ? t("nav.expand") : t("nav.collapse")} onClick={toggleNav}>
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </IconButton>
      </div>

      <nav className="mt-2 flex flex-1 flex-col justify-between overflow-y-auto">
        <div>
          {GROUPS.map((group, index) => (
            <NavSection key={group.labelKey} group={group} collapsed={collapsed} divided={index > 0} />
          ))}
        </div>
        <NavSection group={SYSTEM} collapsed={collapsed} divided />
      </nav>
    </aside>
  );
}
