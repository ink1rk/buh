import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useFloorplan } from "@/shared/api/queries";
import type { FloorplanItem } from "@/shared/api/types";
import { Badge, type Tone } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function meters(mm: number) {
  return (mm / 1000).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function footprint(item: { width: number; height: number; rotation: number }) {
  if (item.rotation % 180 === 90) return { width: item.height, height: item.width };
  return { width: item.width, height: item.height };
}

function kindTone(kind: string): Tone {
  if (kind === "RACK") return "accent";
  if (kind === "POWER") return "warn";
  return "neutral";
}

export function FloorplanPage() {
  const { planId } = useParams();
  const { t, te } = useI18n();
  const { data, isLoading } = useFloorplan(planId);
  const canvas = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<{ id: string; x: number; y: number } | null>(null);

  const save = useApiMutation(
    (body: { itemId: string; x: number; y: number }) =>
      mutations.moveFloorplanItem(planId ?? "", body.itemId, { x: body.x, y: body.y }),
    [keys.floorplan(planId ?? ""), keys.floorplans],
    {
      onSuccess: () => toast.success(t("app.saved")),
      onError: (err) => toast.error(describeError(err, t)),
    },
  );
  const place = useApiMutation(
    (body: { ci_id: string; x: number; y: number }) =>
      mutations.placeFloorplanItem(planId ?? "", body),
    [keys.floorplan(planId ?? ""), keys.floorplans],
    {
      onSuccess: () => toast.success(t("app.saved")),
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  if (isLoading || !data || !planId) {
    return <p className="text-sm text-muted">{t("app.loading")}</p>;
  }

  const plan = data.plan;
  const shown = data.items.map((item) =>
    draft && draft.id === item.id ? { ...item, x: draft.x, y: draft.y } : item,
  );

  function snap(value: number) {
    return Math.max(0, Math.round(value / 50) * 50);
  }

  function startDrag(item: FloorplanItem, event: ReactPointerEvent<HTMLButtonElement>) {
    const bounds = canvas.current?.getBoundingClientRect();
    if (!bounds) return;
    const area = bounds;
    const originX = event.clientX;
    const originY = event.clientY;
    const startX = item.x;
    const startY = item.y;
    event.currentTarget.setPointerCapture(event.pointerId);

    function move(next: PointerEvent) {
      const dx = ((next.clientX - originX) / area.width) * plan.width_mm;
      const dy = ((next.clientY - originY) / area.height) * plan.height_mm;
      setDraft({ id: item.id, x: snap(startX + dx), y: snap(startY + dy) });
    }
    function up(next: PointerEvent) {
      event.currentTarget.removeEventListener("pointermove", move);
      event.currentTarget.removeEventListener("pointerup", up);
      const dx = ((next.clientX - originX) / area.width) * plan.width_mm;
      const dy = ((next.clientY - originY) / area.height) * plan.height_mm;
      setDraft(null);
      save.mutate({ itemId: item.id, x: snap(startX + dx), y: snap(startY + dy) });
    }
    event.currentTarget.addEventListener("pointermove", move);
    event.currentTarget.addEventListener("pointerup", up);
  }

  return (
    <div data-testid="floorplan-page">
      <PageHeader
        title={plan.name}
        subtitle={`${plan.location_name ?? ""} · ${meters(plan.width_mm)} × ${meters(plan.height_mm)} м`}
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
        <div
          ref={canvas}
          data-testid="floorplan-canvas"
          className="relative overflow-hidden rounded-lg border border-app bg-[rgb(var(--surface-muted))]"
          style={{ aspectRatio: `${plan.width_mm} / ${plan.height_mm}` }}
        >
          {shown.map((item) => {
            const size = footprint(item);
            return (
              <button
                key={item.id}
                type="button"
                data-testid="floorplan-item"
                data-code={item.code ?? ""}
                data-x={item.x}
                data-y={item.y}
                className="absolute flex flex-col justify-end overflow-hidden rounded border border-app bg-surface px-1 py-0.5 text-left shadow-sm"
                style={{
                  left: `${(item.x / plan.width_mm) * 100}%`,
                  top: `${(item.y / plan.height_mm) * 100}%`,
                  width: `${(size.width / plan.width_mm) * 100}%`,
                  height: `${(size.height / plan.height_mm) * 100}%`,
                }}
                onPointerDown={(event) => startDrag(item, event)}
              >
                <span className="truncate text-[11px] font-semibold">{item.name}</span>
                <span className="truncate font-mono text-[10px] text-muted">{item.code}</span>
              </button>
            );
          })}
        </div>
        <Panel title={t("floorplans.available")}>
          {data.available.length === 0 ? (
            <p className="text-sm text-muted">{t("floorplans.availableEmpty")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {data.available.map((item, index) => (
                <li key={item.ci_id} className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{item.name}</div>
                    <Badge tone={kindTone(item.item_kind)}>{te("floorplanKind", item.item_kind)}</Badge>
                  </div>
                  <Button
                    size="sm"
                    data-testid={`place-${item.code ?? item.ci_id}`}
                    disabled={place.isPending}
                    onClick={() =>
                      place.mutate({ ci_id: item.ci_id, x: 200, y: 200 + index * 1200 })
                    }
                  >
                    {t("floorplans.place")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
