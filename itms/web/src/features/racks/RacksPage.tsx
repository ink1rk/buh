import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useLocations, useRacks } from "@/shared/api/queries";
import type { RackSummary } from "@/shared/api/types";
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

function RackCard({ rack, onOpen }: { rack: RackSummary; onOpen: () => void }) {
  const { t, te } = useI18n();
  const used = Math.min(rack.used_front, rack.u_height);
  const fill = rack.u_height > 0 ? (used / rack.u_height) * 100 : 0;
  const powerHot = rack.max_power_w != null && rack.power_w > rack.max_power_w;
  return (
    <button type="button" onClick={onOpen} className="card flex gap-3 p-3 text-left transition-colors hover:bg-[rgb(var(--surface-muted))]">
      <span
        className="relative h-36 w-12 shrink-0 overflow-hidden rounded-md border border-app bg-[rgb(var(--bg))]"
        aria-hidden
      >
        <span
          className="absolute inset-x-1 bottom-1 rounded-sm bg-[rgb(var(--accent))]"
          style={{ height: `${Math.max(fill, used > 0 ? 8 : 0)}%` }}
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-mono text-xs text-muted">{rack.code ?? "—"}</span>
        <span className="mt-0.5 block truncate text-sm font-semibold">{rack.name}</span>
        <span className="mt-1 block truncate text-xs text-muted">{rack.location_path ?? "—"}</span>
        <span className="mt-2 block text-xs text-muted">{te("rackFormFactor", rack.form_factor)}</span>
        <span className="mt-2 block text-sm tabular-nums">
          {used}/{rack.u_height} U
        </span>
        <span className="block text-xs text-muted">
          {t("racks.free")} {t("racks.units", { n: rack.largest_free_front })}
        </span>
        <span className={`mt-1 block font-mono text-xs tabular-nums ${powerHot ? "text-[rgb(var(--danger))]" : "text-muted"}`}>
          {rack.power_w}
          {rack.max_power_w != null ? ` / ${rack.max_power_w}` : ""} Вт
        </span>
      </span>
    </button>
  );
}

export function RacksPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useRacks();
  const [creating, setCreating] = useState(false);
  const racks = data ?? [];

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
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {racks.map((rack) => (
            <RackCard key={rack.id} rack={rack} onOpen={() => navigate(`/racks/${rack.id}`)} />
          ))}
        </div>
      )}
      <CreateRackDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
