import {
  Boxes,
  FileText,
  History,
  LayoutDashboard,
  Layers,
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
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { cn } from "@/shared/lib/cn";
import { useUiStore } from "@/shared/store/ui";
import { IconButton } from "@/shared/ui/Button";

interface NavItem {
  to: string;
  labelKey: TranslationKey;
  icon: ComponentType<{ size?: number }>;
}

const PRIMARY: NavItem[] = [
  { to: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/ci", labelKey: "nav.objects", icon: Boxes },
  { to: "/devices", labelKey: "nav.devices", icon: Server },
  { to: "/network", labelKey: "nav.network", icon: Network },
  { to: "/ipam", labelKey: "nav.ipam", icon: Router },
  { to: "/diagrams", labelKey: "nav.diagrams", icon: Workflow },
  { to: "/locations", labelKey: "nav.locations", icon: MapPin },
  { to: "/documents", labelKey: "nav.documents", icon: FileText },
  { to: "/directory", labelKey: "nav.directory", icon: Users },
];

const SECONDARY: NavItem[] = [
  { to: "/catalog", labelKey: "nav.catalog", icon: Layers },
  { to: "/audit", labelKey: "nav.audit", icon: History },
  { to: "/imports", labelKey: "nav.imports", icon: Upload },
  { to: "/settings", labelKey: "nav.settings", icon: Settings },
];

function NavSection({ items, collapsed }: { items: NavItem[]; collapsed: boolean }) {
  const { t } = useI18n();
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((item) => {
        const Icon = item.icon;
        const label = t(item.labelKey);
        return (
          <li key={item.to}>
            <NavLink
              to={item.to}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                  collapsed && "justify-center px-0",
                  isActive
                    ? "bg-[rgb(var(--accent-soft))] font-medium text-[rgb(var(--accent))]"
                    : "text-muted hover:bg-[rgb(var(--surface-muted))] hover:text-app",
                )
              }
            >
              <Icon size={16} />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

export function Sidebar() {
  const { t } = useI18n();
  const collapsed = useUiStore((state) => state.navCollapsed);
  const toggleNav = useUiStore((state) => state.toggleNav);

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col gap-3 border-r border-app bg-surface py-3 transition-[width]",
        collapsed ? "w-14 px-2" : "w-56 px-3",
      )}
    >
      <div className={cn("flex items-center", collapsed ? "justify-center" : "justify-between")}>
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-sm font-semibold tracking-tight">{t("app.name")}</p>
            <p className="truncate text-[0.7rem] text-muted">{t("app.tagline")}</p>
          </div>
        )}
        <IconButton label={collapsed ? t("nav.expand") : t("nav.collapse")} onClick={toggleNav}>
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </IconButton>
      </div>

      <nav className="flex flex-1 flex-col justify-between">
        <NavSection items={PRIMARY} collapsed={collapsed} />
        <NavSection items={SECONDARY} collapsed={collapsed} />
      </nav>
    </aside>
  );
}
