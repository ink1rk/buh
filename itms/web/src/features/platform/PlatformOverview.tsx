import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { usePlatform } from "@/shared/api/queries";
import { PageHeader, Panel, Spinner } from "@/shared/ui/Layout";

const CARDS = [
  { key: "clusters", to: "/office/platform/k8s", label: "platform.k8s" },
  { key: "mcp", to: "/office/platform/mcp", label: "platform.mcp" },
  { key: "agents", to: "/office/platform/agents", label: "platform.agents" },
  { key: "routes", to: "/office/platform/routes", label: "platform.routes" },
  { key: "vlans", to: "/office/platform/vlans", label: "platform.vlans" },
  { key: "vms", to: "/office/platform/vms", label: "platform.vms" },
] as const;

export function PlatformOverview() {
  const { t, te } = useI18n();
  const { data, isLoading } = usePlatform();
  if (isLoading || !data) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("nav.platform")} subtitle={t("platform.overviewHint")} />
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {CARDS.map((card) => (
          <Link key={card.key} to={card.to} className="card px-3.5 py-3 hover:bg-[rgb(var(--surface-muted))]">
            <p className="text-[0.7rem] font-medium tracking-[0.08em] text-muted uppercase">
              {t(card.label)}
            </p>
            <p className="mt-1.5 text-2xl font-semibold tabular-nums">{data.counts[card.key]}</p>
          </Link>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("platform.routeMap")}>
          {data.routes.length === 0 ? (
            <p className="text-sm text-muted">{t("platform.routeEmpty")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.routes.map((route) => (
                <li key={route.id} className="rounded-md border border-app px-3 py-2 text-sm">
                  <p className="font-medium">{route.name}</p>
                  <p className="mt-1 font-mono text-xs">
                    {route.host}
                    {route.path} → {route.target_name ?? t("platform.targetMissing")}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {te("routeTarget", route.target_kind)}
                    {route.vlan_label ? ` · VLAN ${route.vlan_label}` : ""}
                    {route.project_name ? ` · ${route.project_name}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={t("platform.where")}>
          {data.clusters.length === 0 && data.agents.length === 0 ? (
            <p className="text-sm text-muted">{t("app.empty")}</p>
          ) : (
            <ul className="flex flex-col gap-3 text-sm">
              {data.clusters.map((cluster) => (
                <li key={cluster.id}>
                  <p className="font-medium">{cluster.name}</p>
                  <p className="text-xs text-muted">
                    {te("platformEnv", cluster.environment)}
                    {cluster.version ? ` · ${cluster.version}` : ""}
                  </p>
                  <ul className="mt-1 ml-3 text-xs text-muted">
                    {data.mcp
                      .filter((item) => item.cluster_id === cluster.id)
                      .map((item) => (
                        <li key={item.id}>MCP · {item.name}</li>
                      ))}
                  </ul>
                </li>
              ))}
              {data.agents.map((agent) => (
                <li key={agent.id} className="text-xs">
                  <span className="text-sm font-medium">{agent.name}</span>
                  <span className="text-muted">
                    {" "}
                    · {te("agentKind", agent.kind)}
                    {agent.mcp_names.length ? ` · ${agent.mcp_names.join(", ")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
