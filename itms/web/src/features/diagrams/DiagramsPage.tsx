import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useDiagrams,
  useLocations,
} from "@/shared/api/queries";
import type { DiagramSummary } from "@/shared/api/types";
import { Badge } from "@/shared/ui/Badge";
import { Button, IconButton } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Checkbox, Field, Input, Select } from "@/shared/ui/Field";
import { FormError, PageHeader } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function CreateDiagramDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data: locations } = useLocations();
  const [name, setName] = useState("");
  const [diagramType, setDiagramType] = useState("NETWORK");
  const [locationId, setLocationId] = useState("");
  const [autofill, setAutofill] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createDiagram(body),
    [keys.diagrams],
    {
      onSuccess: (created) => {
        toast.success(t("app.created"));
        setName("");
        setError(null);
        onClose();
        navigate(`/diagrams/${created.id}`);
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  const locationOptions = (locations ?? []).map((item) => ({ value: item.id, label: item.path }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("diagrams.create")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                name: name.trim(),
                diagram_type: diagramType,
                location_id: locationId || null,
                autofill: autofill && Boolean(locationId),
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("diagrams.name")} required htmlFor="diagram-name">
          <Input
            id="diagram-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
          />
        </Field>
        <Field label={t("diagrams.type")} htmlFor="diagram-type">
          <Select
            id="diagram-type"
            value={diagramType}
            options={["NETWORK", "LOGICAL"].map((value) => ({
              value,
              label: te("diagramType", value),
            }))}
            onChange={(event) => setDiagramType(event.target.value)}
          />
        </Field>
        <Field label={t("diagrams.location")} hint={t("diagrams.locationHint")} htmlFor="diagram-location">
          <Select
            id="diagram-location"
            value={locationId}
            placeholder={t("app.optional")}
            options={locationOptions}
            onChange={(event) => setLocationId(event.target.value)}
          />
        </Field>
        <Checkbox
          label={t("diagrams.autofill")}
          checked={autofill}
          onChange={(event) => setAutofill(event.target.checked)}
        />
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

export function DiagramsPage() {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useDiagrams();
  const { data: locations } = useLocations();
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<DiagramSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remove = useApiMutation((id: string) => mutations.deleteDiagram(id), [keys.diagrams], {
    onSuccess: () => {
      toast.success(t("app.saved"));
      setRemoving(null);
    },
    onError: (err) => setError(describeError(err, t)),
  });

  const pathOf = (id: string | null) =>
    locations?.find((item) => item.id === id)?.path ?? "—";

  const columns: Array<Column<DiagramSummary>> = [
    {
      key: "name",
      header: t("diagrams.name"),
      render: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "type",
      header: t("diagrams.type"),
      width: "140px",
      render: (row) => <Badge tone="accent">{te("diagramType", row.diagram_type)}</Badge>,
    },
    {
      key: "location",
      header: t("diagrams.location"),
      render: (row) => <span className="text-muted">{pathOf(row.location_id)}</span>,
    },
    {
      key: "actions",
      header: "",
      width: "48px",
      align: "right",
      render: (row) => (
        <IconButton
          label={t("app.delete")}
          onClick={(event) => {
            event.stopPropagation();
            setError(null);
            setRemoving(row);
          }}
        >
          <Trash2 size={14} />
        </IconButton>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t("diagrams.title")}
        subtitle={t("diagrams.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>
            {t("diagrams.create")}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(row) => row.id}
        loading={isLoading}
        emptyTitle={t("diagrams.empty")}
        emptyHint={t("diagrams.emptyHint")}
        onRowClick={(row) => navigate(`/diagrams/${row.id}`)}
      />
      <CreateDiagramDialog open={creating} onClose={() => setCreating(false)} />
      <Dialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        width="sm"
        title={t("diagrams.deleteTitle")}
        description={t("diagrams.deleteHint")}
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>{t("app.cancel")}</Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => removing && remove.mutate(removing.id)}
            >
              {t("app.delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm">{removing?.name}</p>
        <FormError message={error} />
      </Dialog>
    </>
  );
}
