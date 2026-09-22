import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useLocations, useRacks } from "@/shared/api/queries";
import type { RackSummary } from "@/shared/api/types";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, PageHeader } from "@/shared/ui/Layout";
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

export function RacksPage() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useRacks();
  const [creating, setCreating] = useState(false);

  const columns: Array<Column<RackSummary>> = [
    {
      key: "name",
      header: t("racks.name"),
      render: (row) => (
        <span className="font-medium">
          {row.name}
          {row.code && <span className="ml-2 font-mono text-xs text-muted">{row.code}</span>}
        </span>
      ),
    },
    {
      key: "location",
      header: t("diagrams.location"),
      render: (row) => <span className="text-muted">{row.location_path ?? "—"}</span>,
    },
    {
      key: "u",
      header: "U",
      width: "120px",
      render: (row) => (
        <span className="tabular-nums">
          {row.used_front}/{row.u_height}
        </span>
      ),
    },
    {
      key: "free",
      header: t("racks.largest"),
      render: (row) => <span className="tabular-nums">{t("racks.units", { n: row.largest_free_front })}</span>,
    },
    {
      key: "power",
      header: t("racks.power"),
      render: (row) => (
        <span className="tabular-nums text-muted">
          {row.power_w}
          {row.max_power_w != null ? ` / ${row.max_power_w} Вт` : " Вт"}
        </span>
      ),
    },
    {
      key: "type",
      header: t("diagrams.type"),
      width: "110px",
      render: (row) => te("rackFormFactor", row.form_factor),
    },
  ];

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
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(row) => row.id}
        loading={isLoading}
        emptyTitle={t("racks.empty")}
        emptyHint={t("racks.emptyHint")}
        onRowClick={(row) => navigate(`/racks/${row.id}`)}
      />
      <CreateRackDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
