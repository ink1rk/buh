import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useFloorplans, useLocations } from "@/shared/api/queries";
import type { FloorplanSummary } from "@/shared/api/types";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, PageHeader } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function CreatePlanDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data: locations } = useLocations();
  const [name, setName] = useState("");
  const [locationId, setLocationId] = useState("");
  const [width, setWidth] = useState("8000");
  const [height, setHeight] = useState("5000");
  const [error, setError] = useState<string | null>(null);
  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createFloorplan(body),
    [keys.floorplans],
    {
      onSuccess: (created) => {
        toast.success(t("app.created"));
        onClose();
        navigate(`/floorplans/${created.plan.id}`);
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog open={open} onClose={onClose} width="sm" title={t("floorplans.create")}>
      <div className="flex flex-col gap-3">
        <Field label={t("floorplans.name")} htmlFor="plan-name">
          <Input id="plan-name" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("floorplans.location")} htmlFor="plan-location">
          <Select
            id="plan-location"
            value={locationId}
            placeholder="—"
            options={(locations ?? []).map((item) => ({ value: item.id, label: item.path }))}
            onChange={(event) => setLocationId(event.target.value)}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("floorplans.width")} htmlFor="plan-width">
            <Input id="plan-width" value={width} onChange={(event) => setWidth(event.target.value)} />
          </Field>
          <Field label={t("floorplans.height")} htmlFor="plan-height">
            <Input id="plan-height" value={height} onChange={(event) => setHeight(event.target.value)} />
          </Field>
        </div>
        <FormError message={error} />
        <Button
          variant="primary"
          disabled={!name.trim() || !locationId || create.isPending}
          onClick={() =>
            create.mutate({
              name: name.trim(),
              location_id: locationId,
              width_mm: Number(width),
              height_mm: Number(height),
            })
          }
        >
          {t("floorplans.create")}
        </Button>
      </div>
    </Dialog>
  );
}

export function FloorplansPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useFloorplans();
  const [creating, setCreating] = useState(false);
  const columns: Array<Column<FloorplanSummary>> = [
    {
      key: "name",
      header: t("floorplans.name"),
      render: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "location",
      header: t("floorplans.location"),
      render: (row) => <span className="text-muted">{row.location_name ?? "—"}</span>,
    },
    {
      key: "size",
      header: t("floorplans.size"),
      render: (row) => (
        <span className="tabular-nums">
          {row.width_mm / 1000} × {row.height_mm / 1000} м
        </span>
      ),
    },
    {
      key: "items",
      header: t("floorplans.items"),
      render: (row) => <span className="tabular-nums">{row.item_count}</span>,
    },
  ];

  return (
    <div data-testid="floorplans-page">
      <PageHeader
        title={t("floorplans.title")}
        subtitle={t("floorplans.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>
            {t("floorplans.create")}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(row) => row.id}
        loading={isLoading}
        emptyTitle={t("floorplans.empty")}
        emptyHint={t("floorplans.emptyHint")}
        onRowClick={(row) => navigate(`/floorplans/${row.id}`)}
      />
      <CreatePlanDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
