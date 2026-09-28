import { NavLink, Outlet } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { cn } from "@/shared/lib/cn";

const LINKS: Array<{ to: string; labelKey: TranslationKey; end?: boolean }> = [
  { to: "/office/platform", labelKey: "platform.overview", end: true },
  { to: "/office/platform/k8s", labelKey: "platform.k8s" },
  { to: "/office/platform/mcp", labelKey: "platform.mcp" },
  { to: "/office/platform/agents", labelKey: "platform.agents" },
  { to: "/office/platform/routes", labelKey: "platform.routes" },
  { to: "/office/platform/vlans", labelKey: "platform.vlans" },
  { to: "/office/platform/vms", labelKey: "platform.vms" },
];

export function PlatformFrame() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-4" data-testid="platform">
      <nav className="flex gap-1 overflow-x-auto border-b border-app" aria-label={t("nav.platform")}>
        {LINKS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-[13px] font-medium",
                isActive
                  ? "border-[rgb(var(--accent))] text-app"
                  : "border-transparent text-muted hover:text-app",
              )
            }
          >
            {t(item.labelKey)}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
