import {
  Boxes,
  FileText,
  FolderKanban,
  GalleryVertical,
  History,
  BarChart3,
  LayoutDashboard,
  Layers,
  Map,
  MapPin,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Router,
  Server,
  Settings,
  Upload,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { cn } from "@/shared/lib/cn";
import { useUiStore } from "@/shared/store/ui";
import { IconButton } from "@/shared/ui/Button";
import { Mark } from "@/shared/ui/Mark";

interface NavItem {
  to: string;
  labelKey: TranslationKey;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
}

interface NavGroup {
  labelKey: TranslationKey;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    labelKey: "nav.groupOverview",
    items: [
      { to: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard },
      { to: "/analytics", labelKey: "nav.analytics", icon: BarChart3 },
    ],
  },
  {
    labelKey: "nav.groupInfrastructure",
    items: [
      { to: "/ci", labelKey: "nav.objects", icon: Boxes },
      { to: "/devices", labelKey: "nav.devices", icon: Server },
      { to: "/network", labelKey: "nav.network", icon: Network },
      { to: "/ipam", labelKey: "nav.ipam", icon: Router },
      { to: "/diagrams", labelKey: "nav.diagrams", icon: Workflow },
      { to: "/racks", labelKey: "nav.racks", icon: GalleryVertical },
      { to: "/floorplans", labelKey: "nav.floorplans", icon: Map },
      { to: "/power", labelKey: "nav.power", icon: Zap },
      { to: "/locations", labelKey: "nav.locations", icon: MapPin },
    ],
  },
  {
    labelKey: "nav.groupWork",
    items: [
      { to: "/projects", labelKey: "nav.projects", icon: FolderKanban },
      { to: "/documents", labelKey: "nav.documents", icon: FileText },
      { to: "/directory", labelKey: "nav.directory", icon: Users },
    ],
  },
];

const SYSTEM: NavGroup = {
  labelKey: "nav.groupSystem",
  items: [
    { to: "/catalog", labelKey: "nav.catalog", icon: Layers },
    { to: "/audit", labelKey: "nav.audit", icon: History },
    { to: "/imports", labelKey: "nav.imports", icon: Upload },
    { to: "/settings", labelKey: "nav.settings", icon: Settings },
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
  return (
    <div className={cn("flex flex-col", divided && (collapsed ? "mt-2" : "mt-1"))}>
      {collapsed ? (
        divided && <div className="mx-auto mb-2 h-px w-5 bg-[rgb(var(--border))]" />
      ) : (
        <p className="px-2.5 pt-3 pb-1 text-[0.65rem] font-semibold tracking-[0.16em] text-muted uppercase">
          {t(group.labelKey)}
        </p>
      )}
      <ul className="flex flex-col gap-0.5">
        {group.items.map((item) => {
          const Icon = item.icon;
          const label = t(item.labelKey);
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                title={collapsed ? label : undefined}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                    collapsed && "justify-center px-0",
                    isActive
                      ? "bg-[rgb(var(--accent-soft))] font-semibold text-[rgb(var(--accent))]"
                      : "text-muted hover:bg-[rgb(var(--surface-muted))] hover:text-app",
                  )
                }
              >
                <Icon size={16} strokeWidth={1.75} />
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
        collapsed ? "w-[4.25rem] px-2" : "w-60 px-3",
      )}
    >
      <div className={cn("flex items-center gap-2.5 px-1", collapsed && "flex-col")}>
        <Mark size={collapsed ? 26 : 30} />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <p className="text-[0.95rem] leading-tight font-semibold tracking-tight">{t("app.name")}</p>
            <p className="truncate text-[0.68rem] leading-4 text-muted">{t("app.tagline")}</p>
          </div>
        )}
        <IconButton label={collapsed ? t("nav.expand") : t("nav.collapse")} onClick={toggleNav}>
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </IconButton>
      </div>

      <nav className="mt-3 flex flex-1 flex-col justify-between overflow-y-auto">
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
