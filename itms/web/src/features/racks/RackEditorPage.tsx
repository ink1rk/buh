import { useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import { ApiError, type Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useRack } from "@/shared/api/queries";
import type { RackMount, WarehouseItem } from "@/shared/api/types";
import { cn } from "@/shared/lib/cn";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { FormError, PageHeader, Panel, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ReasonField } from "../provenance/ReasonField";

const ROW = 22;

type Face = "FRONT" | "REAR";

interface PlaceBody {
  ci_id: string;
  position_u: number;
  u_height: number;
  face: string;
  zero_u_side?: string | null;
  confirm_warnings?: boolean;
}

function rowTop(unit: number, rackU: number, descending: boolean): number {
  if (descending) return (unit - 1) * ROW;
  return (rackU - unit) * ROW;
}

function blockTop(position: number, height: number, rackU: number, descending: boolean): number {
  const topUnit = descending ? position : position + height - 1;
  return rowTop(topUnit, rackU, descending);
}

function meter(used: number, max: number | null): number | null {
  if (max == null || max <= 0) return null;
  return Math.round((used / max) * 100);
}

function meterTone(pct: number | null): string {
  if (pct == null) return "bg-[rgb(var(--accent))]";
  if (pct > 100) return "bg-[rgb(var(--danger))]";
  if (pct > 80) return "bg-[rgb(var(--warn))]";
  return "bg-[rgb(var(--ok))]";
}

function Meter({ label, used, max, unit }: { label: string; used: number; max: number | null; unit: string }) {
  const pct = meter(used, max);
  const tone = meterTone(pct);
  return (
    <div>
      <div className="flex justify-between text-xs text-muted">
        <span>{label}</span>
        <span className="tabular-nums">
          {used}
          {max != null ? ` / ${max}` : ""} {unit}
        </span>
      </div>
      {pct != null && (
        <div className="mt-1 h-1.5 overflow-hidden rounded bg-[rgb(var(--surface-muted))]">
          <div className={cn("h-full", tone)} style={{ width: `${Math.min(pct, 100)}%` }} />
        </div>
      )}
    </div>
  );
}

export function RackEditorPage() {
  const { rackId = "" } = useParams();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useRack(rackId);
  const [face, setFace] = useState<Face>("FRONT");
  const [selected, setSelected] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [reason, setReason] = useState<Provenance>({});
  const [pending, setPending] = useState<PlaceBody | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function commit(body: PlaceBody) {
    setBusy(true);
    try {
      const next = await mutations.placeMount(rackId, body, reason);
      queryClient.setQueryData(keys.rack(rackId), next);
      void queryClient.invalidateQueries({ queryKey: keys.racks });
      setPending(null);
      setMessage(null);
      setSelected(null);
      toast.success(t("app.saved"));
    } catch (err) {
      if (err instanceof ApiError && err.code === "provenance_required") {
        setPending(body);
      } else if (
        err instanceof ApiError &&
        ["weight_exceeded", "power_exceeded", "depth_exceeded", "placement_warning"].includes(err.code)
      ) {
        setPending({ ...body, confirm_warnings: true });
      }
      setMessage(describeError(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function extract(mount: RackMount, toStock: boolean) {
    setBusy(true);
    try {
      const next = await mutations.removeMount(rackId, mount.id, toStock, reason);
      queryClient.setQueryData(keys.rack(rackId), next);
      void queryClient.invalidateQueries({ queryKey: keys.racks });
      setMessage(null);
      toast.success(t("app.saved"));
    } catch (err) {
      setMessage(describeError(err, t));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!data) {
    return (
      <Panel>
        <p className="text-sm">{error ? describeError(error, t) : t("errors.not_found")}</p>
      </Panel>
    );
  }

  const rack = data.rack;
  const visible = data.mounts.filter(
    (mount) => mount.u_height > 0 && (mount.face === face || mount.face === "FULL"),
  );
  const zero = data.mounts.filter((mount) => mount.u_height === 0);
  const free = face === "FRONT" ? data.free_front : data.free_rear;
  const selectedItem = data.warehouse.find((item) => item.ci_id === selected);
  const hoverSpan = hover != null && selectedItem ? Array.from({ length: Math.max(selectedItem.u_height, 1) }, (_, index) => hover + index) : [];

  function placeZero(ciId: string, side: "LEFT" | "RIGHT") {
    void commit({ ci_id: ciId, position_u: 1, u_height: 0, face, zero_u_side: side });
  }

  function onDropUnit(unit: number, event: DragEvent) {
    event.preventDefault();
    const ciId = event.dataTransfer.getData("text/ci");
    const height = Number(event.dataTransfer.getData("text/height") || "1");
    setHover(null);
    if (!ciId) return;
    void commit({
      ci_id: ciId,
      position_u: unit,
      u_height: height,
      face,
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        title={rack.name}
        subtitle={[rack.code, rack.location_path, `${rack.u_height}U`].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant={face === "FRONT" ? "primary" : "secondary"} onClick={() => setFace("FRONT")}>
              {t("racks.front")}
            </Button>
            <Button variant={face === "REAR" ? "primary" : "secondary"} onClick={() => setFace("REAR")}>
              {t("racks.rear")}
            </Button>
          </>
        }
      />
      <p className="text-xs text-muted">{t("racks.selectHint")}</p>
      <FormError message={message} />
      {pending && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <ReasonField value={reason} onChange={setReason} required />
          </div>
          <Button variant="primary" disabled={busy} onClick={() => void commit(pending)}>
            {pending.confirm_warnings ? t("racks.confirmPlace") : t("racks.retry")}
          </Button>
        </div>
      )}
      <div className="grid items-start gap-3 lg:grid-cols-[240px_minmax(0,1fr)_220px]">
        <Panel title={t("racks.warehouse")} bodyClassName="flex max-h-[70vh] flex-col gap-1 overflow-y-auto">
          {data.warehouse.length === 0 && <p className="text-xs text-muted">{t("app.empty")}</p>}
          {data.warehouse.map((item) => (
            <WarehouseRow
              key={item.ci_id}
              item={item}
              active={selected === item.ci_id}
              onSelect={() => setSelected(item.ci_id)}
            />
          ))}
        </Panel>

        <Panel bodyClassName="overflow-x-auto">
          <div className="flex gap-2">
            <ZeroRail
              title={t("racks.zeroLeft")}
              mounts={zero.filter((mount) => mount.zero_u_side === "LEFT")}
              onDrop={(ciId) => placeZero(ciId, "LEFT")}
              labelOf={(mount) => mount.name}
            />
            <div className="relative min-w-[280px] flex-1" style={{ height: rack.u_height * ROW }}>
              {Array.from({ length: rack.u_height }, (_, index) => {
                const unit = rack.descending_units ? index + 1 : rack.u_height - index;
                const hot = hoverSpan.includes(unit);
                return (
                  <button
                    key={unit}
                    type="button"
                    className={cn(
                      "absolute right-0 left-8 border-b border-app text-left",
                      hot && "bg-[rgb(var(--accent-soft))]",
                    )}
                    style={{ top: index * ROW, height: ROW }}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setHover(unit);
                    }}
                    onDragLeave={() => setHover(null)}
                    onDrop={(event) => onDropUnit(unit, event)}
                    onClick={() => {
                      if (!selectedItem) return;
                      void commit({
                        ci_id: selectedItem.ci_id,
                        position_u: unit,
                        u_height: Math.max(selectedItem.u_height, 1),
                        face,
                      });
                    }}
                  >
                    <span className="absolute -left-8 w-7 text-right font-mono text-[10px] text-muted">{unit}</span>
                  </button>
                );
              })}
              {visible.map((mount) => (
                <Link
                  key={mount.id}
                  to={`/ci/${mount.ci_id}`}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData("text/ci", mount.ci_id);
                    event.dataTransfer.setData("text/height", String(mount.u_height));
                  }}
                  className={cn(
                    "absolute right-0 left-8 flex items-center justify-between gap-2 overflow-hidden rounded border border-l-4 border-app bg-surface px-2 text-xs",
                    mount.face === "FULL" && "border-l-[rgb(var(--danger))]",
                    mount.is_reservation && "border-dashed opacity-70",
                  )}
                  style={{
                    top: blockTop(mount.position_u, mount.u_height, rack.u_height, rack.descending_units) + 1,
                    height: mount.u_height * ROW - 2,
                  }}
                  title={mount.name}
                >
                  <span className="truncate font-medium">{mount.name}</span>
                  <span className="shrink-0 font-mono text-[10px] text-muted">
                    U{mount.position_u}
                    {mount.u_height > 1 ? `–${mount.position_u + mount.u_height - 1}` : ""}
                  </span>
                </Link>
              ))}
            </div>
            <ZeroRail
              title={t("racks.zeroRight")}
              mounts={zero.filter((mount) => mount.zero_u_side === "RIGHT")}
              onDrop={(ciId) => placeZero(ciId, "RIGHT")}
              labelOf={(mount) => mount.name}
            />
          </div>
          {selected && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => placeZero(selected, "LEFT")}>
                {t("racks.zeroLeft")}
              </Button>
              <Button disabled={busy} onClick={() => placeZero(selected, "RIGHT")}>
                {t("racks.zeroRight")}
              </Button>
            </div>
          )}
        </Panel>

        <div className="flex flex-col gap-3">
          <Panel title={t("racks.used")}>
            <div className="flex flex-col gap-3">
              <Meter label="U" used={face === "FRONT" ? data.capacity.used_front : data.capacity.used_rear} max={data.capacity.u_height} unit="" />
              <Meter label={t("racks.weight")} used={data.capacity.weight_kg} max={data.capacity.max_weight_kg} unit="кг" />
              <Meter label={t("racks.power")} used={data.capacity.power_w} max={data.capacity.max_power_w} unit="Вт" />
            </div>
          </Panel>
          <Panel title={t("racks.free")}>
            <ul className="flex flex-col gap-1 text-xs">
              {free.length === 0 && <li className="text-muted">{t("app.empty")}</li>}
              {free.map((block) => (
                <li key={block.start} className="flex justify-between tabular-nums">
                  <span>
                    U{block.start}
                    {block.length > 1 ? `–${block.start + block.length - 1}` : ""}
                  </span>
                  <span className="text-muted">{t("racks.units", { n: block.length })}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title={t("racks.extract")}>
            <ul className="flex flex-col gap-1">
              {visible.map((mount) => (
                <li key={mount.id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate">{mount.name}</span>
                  <span className="flex gap-1">
                    <Button className="h-6 px-1.5 text-[11px]" disabled={busy} onClick={() => void extract(mount, false)}>
                      {t("racks.extract")}
                    </Button>
                    {mount.status === "ACTIVE" && (
                      <Button className="h-6 px-1.5 text-[11px]" disabled={busy} onClick={() => void extract(mount, true)}>
                        {t("racks.toStock")}
                      </Button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function WarehouseRow({
  item,
  active,
  onSelect,
}: {
  item: WarehouseItem;
  active: boolean;
  onSelect: () => void;
}) {
  const { te, t } = useI18n();
  return (
    <button
      type="button"
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData("text/ci", item.ci_id);
        event.dataTransfer.setData("text/height", String(Math.max(item.u_height, 1)));
      }}
      onClick={onSelect}
      className={cn(
        "rounded border px-2 py-1.5 text-left text-xs",
        active ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent-soft))]" : "border-app hover:bg-[rgb(var(--surface-muted))]",
      )}
    >
      <span className="block truncate font-medium">{item.name}</span>
      <span className="mt-0.5 flex items-center gap-1 text-[10px] text-muted">
        <span className="font-mono">{item.code ?? "—"}</span>
        <Badge tone={toneFor("ciStatus", item.status)}>{te("ciStatus", item.status)}</Badge>
        <span>{item.device_role ? te("deviceRole", item.device_role) : ""}</span>
        <span>{t("racks.units", { n: item.u_height })}</span>
      </span>
    </button>
  );
}

function ZeroRail({
  title,
  mounts,
  onDrop,
  labelOf,
}: {
  title: string;
  mounts: RackMount[];
  onDrop: (ciId: string) => void;
  labelOf: (mount: RackMount) => string;
}) {
  return (
    <div
      className="flex w-16 shrink-0 flex-col gap-1 rounded border border-dashed border-app p-1"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const ciId = event.dataTransfer.getData("text/ci");
        if (ciId) onDrop(ciId);
      }}
    >
      <p className="text-[10px] text-muted">{title}</p>
      {mounts.map((mount) => (
        <Link key={mount.id} to={`/ci/${mount.ci_id}`} className="truncate rounded bg-[rgb(var(--surface-muted))] px-1 py-1 text-[10px]">
          {labelOf(mount)}
        </Link>
      ))}
    </div>
  );
}
