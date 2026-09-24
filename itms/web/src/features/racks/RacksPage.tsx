import { useQueries } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { api } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useFloorplans, useLocations, useRack, useRacks } from "@/shared/api/queries";
import type { FloorplanView, RackSummary } from "@/shared/api/types";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { EmptyState, FormError, PageHeader, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function CreateRackDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data: locations } = useLocations();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [locationId, setLocationId] = useState("");
  const [uHeight, setUHeight] = useState("42");
  const [error, setError] = useState<string | null>(null);

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createRack(body),
    [keys.racks],
    {
      onSuccess: (created) => {
        toast.success(t("app.created"));
        onClose();
        navigate(`/racks/${created.rack.id}`);
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("racks.create")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                name: name.trim(),
                code: code.trim() || null,
                location_id: locationId || null,
                u_height: Number(uHeight) || 42,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("racks.name")} required htmlFor="rack-name">
          <Input id="rack-name" value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("racks.code")} htmlFor="rack-code">
          <Input id="rack-code" value={code} onChange={(event) => setCode(event.target.value)} />
        </Field>
        <Field label={t("racks.height")} htmlFor="rack-u">
          <Input id="rack-u" value={uHeight} onChange={(event) => setUHeight(event.target.value)} />
        </Field>
        <Field label={t("diagrams.location")} htmlFor="rack-location">
          <Select
            id="rack-location"
            value={locationId}
            placeholder={t("app.optional")}
            options={(locations ?? []).map((item) => ({ value: item.id, label: item.path }))}
            onChange={(event) => setLocationId(event.target.value)}
          />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function RackMiniPlan({ rackId }: { rackId: string }) {
  const { t } = useI18n();
  const plans = useFloorplans();
  const views = useQueries({
    queries: (plans.data ?? []).map((plan) => ({
      queryKey: keys.floorplan(plan.id),
      queryFn: () => api.get<FloorplanView>(`/floorplans/${plan.id}`),
    })),
  });
  if (plans.isLoading || views.some((query) => query.isLoading)) return <Spinner className="h-4 w-4" />;
  const view = views.map((query) => query.data).find((item) => item?.items.some((row) => row.ci_id === rackId));
  if (!view) return <p className="text-xs text-muted">{t("racks.noPlan")}</p>;
  return (
    <Link to={`/floorplans/${view.plan.id}`} className="block" data-testid="rack-mini-plan">
      <div
        className="relative overflow-hidden rounded-xl border border-app bg-[rgb(var(--bg))]"
        style={{ aspectRatio: `${view.plan.width_mm} / ${view.plan.height_mm}` }}
      >
        {view.items.map((item) => (
          <span
            key={item.id}
            className={`absolute rounded-sm border ${
              item.ci_id === rackId
                ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent)/0.55)]"
                : "border-app bg-[rgb(var(--surface-muted))]"
            }`}
            style={{
              left: `${(item.x / view.plan.width_mm) * 100}%`,
              top: `${(item.y / view.plan.height_mm) * 100}%`,
              width: `${Math.max(item.width, 1) / view.plan.width_mm * 100}%`,
              height: `${Math.max(item.height, 1) / view.plan.height_mm * 100}%`,
            }}
          />
        ))}
      </div>
      <p className="mt-1 truncate text-[11px] text-muted">{view.plan.name}</p>
    </Link>
  );
}

function RackDetail({ rack, onOpen }: { rack: RackSummary; onOpen: () => void }) {
  const { t, te } = useI18n();
  const elevation = useRack(rack.id);
  const detail = elevation.data?.rack;
  const used = Math.min(rack.used_front, rack.u_height);
  const occupancy = rack.u_height > 0 ? used / rack.u_height : 0;
  const glow = occupancy >= 0.9 ? "glow-danger" : occupancy >= 0.7 ? "glow-warn" : occupancy > 0 ? "glow-ok" : "";
  const ring = 2 * Math.PI * 36;
  const stroke = occupancy >= 0.9 ? "rgb(var(--danger))" : occupancy >= 0.7 ? "rgb(var(--warn))" : "rgb(var(--ok))";
  return (
    <aside className="card flex flex-col gap-4 p-4" data-testid="rack-detail">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] tracking-[0.14em] text-muted uppercase">{t("racks.detail")}</p>
          <h2 className="mt-1 truncate text-base font-semibold">{rack.name}</h2>
          <p className="font-mono text-xs text-muted">{rack.code ?? "—"}</p>
        </div>
        <Button onClick={onOpen}>{t("racks.openEditor")}</Button>
      </header>
      <div className="flex items-center gap-4">
        <svg viewBox="0 0 96 96" className={`h-24 w-24 shrink-0 ${glow}`} aria-hidden>
          <circle cx="48" cy="48" r="36" fill="none" stroke="rgb(var(--bg))" strokeWidth="8" />
          {occupancy > 0 && (
            <circle
              cx="48"
              cy="48"
              r="36"
              fill="none"
              stroke={stroke}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${occupancy * ring} ${ring}`}
              transform="rotate(-90 48 48)"
            />
          )}
          <text x="48" y="53" textAnchor="middle" fill="rgb(var(--text))" fontSize="18" fontWeight="650">
            {used}
          </text>
        </svg>
        <div>
          <p className="text-xs text-muted">{t("racks.occupancy")}</p>
          <p className="text-sm font-medium tabular-nums">
            {used}/{rack.u_height} U
          </p>
          <p className="mt-1 text-xs text-muted">
            {t("racks.free")} {t("racks.units", { n: rack.largest_free_front })}
          </p>
        </div>
      </div>
      <div>
        <h3 className="text-sm font-semibold">{t("racks.characteristics")}</h3>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
          <dt className="text-muted">{t("racks.code")}</dt>
          <dd className="font-mono">{rack.code ?? "—"}</dd>
          <dt className="text-muted">{t("diagrams.location")}</dt>
          <dd>{rack.location_path ?? "—"}</dd>
          <dt className="text-muted">{t("racks.formFactor")}</dt>
          <dd>{te("rackFormFactor", rack.form_factor)}</dd>
          <dt className="text-muted">{t("racks.weight")}</dt>
          <dd className="font-mono tabular-nums">
            {rack.weight_kg}
            {rack.max_weight_kg != null ? ` / ${rack.max_weight_kg}` : ""} кг
          </dd>
          <dt className="text-muted">{t("racks.power")}</dt>
          <dd className="font-mono tabular-nums">
            {rack.power_w}
            {rack.max_power_w != null ? ` / ${rack.max_power_w}` : ""} Вт
          </dd>
          {detail && (
            <>
              <dt className="text-muted">{t("racks.depth")}</dt>
              <dd className="font-mono tabular-nums">{detail.depth_mm}</dd>
            </>
          )}
        </dl>
      </div>
      <RackMiniPlan rackId={rack.id} />
    </aside>
  );
}

function RackCard({ rack, selected, onOpen }: { rack: RackSummary; selected: boolean; onOpen: () => void }) {
  const { t, te } = useI18n();
  const used = Math.min(rack.used_front, rack.u_height);
  const slots = Math.min(Math.max(rack.u_height, 1), 42);
  const filled = rack.u_height > 0 ? Math.round((used / rack.u_height) * slots) : 0;
  const powerHot = rack.max_power_w != null && rack.power_w > rack.max_power_w;
  const showWeight = rack.weight_kg > 0 || rack.max_weight_kg != null;
  const occupancy = rack.u_height > 0 ? used / rack.u_height : 0;
  const glow = occupancy >= 0.9 ? "glow-danger" : occupancy >= 0.7 ? "glow-warn" : "glow-accent";
  const ring = 2 * Math.PI * 18;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-pressed={selected}
      data-testid="rack-card"
      className={`card flex gap-4 p-4 text-left transition-transform hover:-translate-y-px ${selected ? "ring-1 ring-[rgb(var(--accent))]" : ""}`}
    >
      <svg viewBox="0 0 48 48" className={`h-12 w-12 shrink-0 ${rack.u_height > 0 ? glow : ""}`} aria-hidden>
        <circle cx="24" cy="24" r="18" fill="none" stroke="rgb(var(--bg))" strokeWidth="4" />
        <circle
          cx="24"
          cy="24"
          r="18"
          fill="none"
          stroke={occupancy >= 0.9 ? "rgb(var(--danger))" : occupancy >= 0.7 ? "rgb(var(--warn))" : "rgb(var(--accent))"}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${occupancy * ring} ${ring}`}
          transform="rotate(-90 24 24)"
        />
        <text x="24" y="27" textAnchor="middle" fill="rgb(var(--text))" fontSize="11" fontWeight="650">
          {used}
        </text>
      </svg>
      <span className="relative flex h-56 w-16 shrink-0 rounded-lg bg-[rgb(var(--bg))] px-2 py-1.5" aria-hidden>
        <span className="absolute inset-y-2 left-1 w-0.5 rounded-full bg-[rgb(var(--border))]" />
        <span className="absolute inset-y-2 right-1 w-0.5 rounded-full bg-[rgb(var(--border))]" />
        <span className="flex min-h-0 flex-1 flex-col-reverse gap-px">
          {Array.from({ length: slots }, (_, index) => (
            <span
              key={index}
              className={`relative min-h-0 flex-1 rounded-[1px] ${index < filled ? "bg-[rgb(var(--accent))]" : "bg-[rgb(var(--surface-muted))]"}`}
            >
              {index < filled && <span className="absolute top-1/2 right-0.5 h-1 w-1 -translate-y-1/2 rounded-full bg-[rgb(var(--ok))]" />}
            </span>
          ))}
        </span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-mono text-xs text-muted">{rack.code ?? "—"}</span>
        <span className="mt-0.5 block truncate text-sm font-semibold">{rack.name}</span>
        <span className="mt-1 block truncate text-xs text-muted">{rack.location_path ?? "—"}</span>
        <span className="mt-2 block text-xs text-muted">{te("rackFormFactor", rack.form_factor)}</span>
        <span className="mt-3 block text-4xl leading-none font-semibold tracking-tight tabular-nums">
          {used}
          <span className="text-base font-medium text-muted">/{rack.u_height} U</span>
        </span>
        <span className="mt-2 block text-xs text-muted">
          {t("racks.free")} {t("racks.units", { n: rack.largest_free_front })}
        </span>
        {showWeight && (
          <span className="mt-1 block font-mono text-xs text-muted tabular-nums">
            {t("racks.weight")} {rack.weight_kg}
            {rack.max_weight_kg != null ? ` / ${rack.max_weight_kg}` : ""} кг
          </span>
        )}
        <span className={`mt-1 block font-mono text-xs tabular-nums ${powerHot ? "text-[rgb(var(--danger))]" : "text-muted"}`}>
          {rack.power_w}
          {rack.max_power_w != null ? ` / ${rack.max_power_w}` : ""} Вт
        </span>
        {rack.max_power_w != null && rack.max_power_w > 0 && (
          <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-[rgb(var(--bg))]">
            <span
              className={`block h-full rounded-full ${powerHot ? "bg-[rgb(var(--danger))]" : "bg-[rgb(var(--warn))]"}`}
              style={{ width: `${Math.min(100, (rack.power_w / rack.max_power_w) * 100)}%` }}
            />
          </span>
        )}
      </span>
    </button>
  );
}

export function RacksPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useRacks();
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const racks = data ?? [];
  const selected = racks.find((rack) => rack.id === selectedId) ?? null;

  return (
    <>
      <PageHeader
        title={t("racks.title")}
        subtitle={t("racks.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>
            {t("racks.create")}
          </Button>
        }
      />
      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : racks.length === 0 ? (
        <div className="card">
          <EmptyState title={t("racks.empty")} hint={t("racks.emptyHint")} />
        </div>
      ) : (
        <div className={selected ? "grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_22rem]" : ""}>
          <div className="grid gap-3 sm:grid-cols-2">
            {racks.map((rack) => (
              <RackCard
                key={rack.id}
                rack={rack}
                selected={rack.id === selectedId}
                onOpen={() => setSelectedId(rack.id)}
              />
            ))}
          </div>
          {selected && <RackDetail rack={selected} onOpen={() => navigate(`/racks/${selected.id}`)} />}
        </div>
      )}
      <CreateRackDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
