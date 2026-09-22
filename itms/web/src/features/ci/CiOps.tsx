import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useDevice, useDeviceInterfaces, useEmployees, usePower } from "@/shared/api/queries";
import type { Ci, RelatedItem, RelatedMap } from "@/shared/api/types";

function relatedItems(related: RelatedMap | undefined): RelatedItem[] {
  if (!related) return [];
  const items: RelatedItem[] = [];
  for (const [key, value] of Object.entries(related)) {
    if (key === "documents" || !Array.isArray(value)) continue;
    for (const item of value) {
      if (item && typeof item === "object" && "ci" in item) items.push(item as RelatedItem);
    }
  }
  return items;
}

function speedLabel(mbps: number | null): string | null {
  if (mbps == null) return null;
  if (mbps >= 1000 && mbps % 1000 === 0) return `${mbps / 1000} Gbps`;
  return `${mbps} Mbps`;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] tracking-wide text-muted uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

export function CiOps({ ci, related }: { ci: Ci; related: RelatedMap | undefined }) {
  const { t, te } = useI18n();
  const isDevice = ci.ci_type === "DEVICE";
  const device = useDevice(isDevice ? ci.id : undefined);
  const interfaces = useDeviceInterfaces(isDevice ? ci.id : undefined);
  const power = usePower();
  const employees = useEmployees();

  const node = power.data?.nodes.find((item) => item.id === ci.id);
  const links = power.data?.links ?? [];
  const upstream = links.filter((link) => link.target_node_id === ci.id);
  const downstream = links.filter((link) => link.source_node_id === ci.id);
  const owner = employees.data?.find((item) => item.id === ci.owner_employee_id);
  const relations = relatedItems(related).slice(0, 8);
  const ports = (interfaces.data ?? []).slice(0, 6);
  const profile = device.data;

  const showPower = Boolean(node);
  const showDevice = Boolean(profile || ports.length);
  const showRelations = relations.length > 0 || Boolean(owner);
  if (!showPower && !showDevice && !showRelations) return null;

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {showDevice && (
        <section className="surface rounded-lg px-4 py-3">
          <h2 className="text-[13px] font-medium text-muted">{t("nav.network")}</h2>
          {profile && (
            <dl className="mt-2 flex flex-col gap-2">
              {profile.hostname && (
                <Fact label={t("devices.hostname")}>
                  <span className="font-mono text-xs">{profile.hostname}</span>
                </Fact>
              )}
              {profile.mgmt_ip && (
                <Fact label={t("devices.mgmtIp")}>
                  <span className="font-mono text-xs">{profile.mgmt_ip}</span>
                </Fact>
              )}
              <Fact label={t("devices.role")}>{te("deviceRole", profile.device_role)}</Fact>
              {profile.power_nameplate_w != null && (
                <Fact label={t("power.nameplate")}>
                  <span className="font-mono text-xs tabular-nums">{profile.power_nameplate_w} Вт</span>
                </Fact>
              )}
            </dl>
          )}
          {ports.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5">
              {ports.map((port) => {
                const peer = port.connection?.peer;
                const speed = speedLabel(port.speed_mbps);
                return (
                  <li key={port.id} className="text-sm">
                    <span className="font-mono text-xs">{port.name}</span>
                    {peer?.ci_id ? (
                      <>
                        <span className="text-muted"> → </span>
                        <Link to={`/ci/${peer.ci_id}`} className="hover:text-accent">
                          {peer.ci_name ?? peer.interface_name}
                        </Link>
                        <span className="text-muted"> / {peer.interface_name}</span>
                      </>
                    ) : null}
                    {speed && <span className="text-xs text-muted"> · {speed}</span>}
                    {port.ip_addresses[0] && (
                      <span className="mt-0.5 block font-mono text-[11px] text-muted">{port.ip_addresses[0]}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      {showPower && node && (
        <section className="surface rounded-lg px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-[13px] font-medium text-muted">{t("nav.power")}</h2>
            <Link to="/power" className="text-xs text-accent">
              {t("dashboard.openPower")}
            </Link>
          </div>
          <p className="mt-2 text-sm">{te("powerNodeType", node.node_type)}</p>
          <p className="mt-1 font-mono text-xs tabular-nums text-muted">
            {node.inlet_w} Вт
            {node.headroom_w != null ? ` · ${t("dashboard.powerHeadroom").toLowerCase()} ${node.headroom_w} Вт` : ""}
          </p>
          <ul className="mt-3 flex flex-col gap-1 text-sm">
            {upstream.map((link) => (
              <li key={link.id}>
                <Link to={`/ci/${link.source_node_id}`} className="hover:text-accent">
                  {link.source_name ?? "—"}
                </Link>
                <span className="text-muted"> → {node.code ?? node.name}</span>
              </li>
            ))}
            {downstream.map((link) => (
              <li key={link.id}>
                <span className="text-muted">{node.code ?? node.name} → </span>
                <Link to={`/ci/${link.target_node_id}`} className="hover:text-accent">
                  {link.target_name ?? "—"}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {showRelations && (
        <section className="surface rounded-lg px-4 py-3">
          <h2 className="text-[13px] font-medium text-muted">{t("ci.related")}</h2>
          {owner && (
            <p className="mt-2 text-sm">
              <span className="text-muted">{t("ci.owner")}: </span>
              {owner.full_name}
            </p>
          )}
          <ul className="mt-2 flex flex-col gap-1">
            {relations.map((item) => (
              <li key={item.relation_id}>
                <Link to={`/ci/${item.ci.id}`} className="text-sm hover:text-accent">
                  <span className="font-mono text-xs text-muted">{item.ci.code ?? ""}</span>
                  {item.ci.code ? " " : ""}
                  {item.ci.name}
                </Link>
                <span className="ml-2 text-xs text-muted">{te("relationType", item.rel_type)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
