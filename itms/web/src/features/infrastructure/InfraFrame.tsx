import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useI18n, type TranslationKey } from "@/i18n";
import { cn } from "@/shared/lib/cn";

const LINKS: Array<{ to: string; labelKey: TranslationKey; match: string[] }> = [
  { to: "/infrastructure", labelKey: "nav.overview", match: ["/infrastructure"] },
  { to: "/ci", labelKey: "nav.objects", match: ["/ci", "/devices", "/ipam"] },
  { to: "/network", labelKey: "nav.network", match: ["/network"] },
  { to: "/diagrams", labelKey: "nav.diagrams", match: ["/diagrams"] },
  { to: "/datacenter", labelKey: "nav.datacenter", match: ["/datacenter", "/racks", "/floorplans", "/locations"] },
  { to: "/power", labelKey: "nav.power", match: ["/power"] },
  { to: "/virtualization", labelKey: "nav.virtualization", match: ["/virtualization"] },
];

export function InfraFrame() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  return (
    <div className="flex flex-col gap-4">
      <nav className="flex gap-1 overflow-x-auto border-b border-app" aria-label={t("nav.infrastructure")}>
        {LINKS.map((item) => {
          const active = item.match.some(
            (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
          );
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors",
                active
                  ? "border-[rgb(var(--accent))] text-app"
                  : "border-transparent text-muted hover:text-app",
              )}
            >
              {t(item.labelKey)}
            </NavLink>
          );
        })}
      </nav>
      <Outlet />
    </div>
  );
}
