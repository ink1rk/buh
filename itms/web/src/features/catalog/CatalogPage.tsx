import { Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useDeviceModels,
  useManufacturers,
  useMeta,
  type ModelListParams,
} from "@/shared/api/queries";
import type { DeviceModel } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { Button, IconButton } from "@/shared/ui/Button";
import { DataTable, Pagination, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { EmptyState, FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ModelDialog } from "./ModelDialog";

const PAGE_SIZE = 50;

function ManufacturerDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createManufacturer(body),
    [keys.manufacturers],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setName("");
        setUrl("");
        setError(null);
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="sm"
      title={t("catalog.addManufacturer")}
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() =>
              create.mutate({ name: name.trim(), support_url: url.trim() || null, notes: null })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("ci.name")} required>
          <Input value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="URL">
          <Input value={url} onChange={(event) => setUrl(event.target.value)} />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

export function CatalogPage() {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: manufacturers } = useManufacturers();

  const [q, setQ] = useState("");
  const [manufacturerId, setManufacturerId] = useState("");
  const [role, setRole] = useState("");
  const [offset, setOffset] = useState(0);
  const [manufacturerOpen, setManufacturerOpen] = useState(false);
  const [editing, setEditing] = useState<{ id: string | null } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DeviceModel | null>(null);

  const debouncedQ = useDebounced(q, 300);
  const params: ModelListParams = useMemo(
    () => ({
      q: debouncedQ || undefined,
      manufacturer_id: manufacturerId || undefined,
      role: role || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [debouncedQ, manufacturerId, role, offset],
  );
  const { data, isFetching } = useDeviceModels(params);

  const remove = useApiMutation(
    (id: string) => mutations.deleteModel(id),
    [["catalog", "models"]],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setPendingDelete(null);
      },
      onError: (err) => toast.error(describeError(err, t)),
    },
  );

  const editingModel =
    editing?.id ? (data?.items.find((item) => item.id === editing.id) ?? null) : null;

  const columns: Array<Column<DeviceModel>> = [
    {
      key: "manufacturer",
      header: t("catalog.manufacturer"),
      width: "12rem",
      render: (row) => <span className="text-muted">{row.manufacturer.name}</span>,
    },
    {
      key: "model",
      header: t("catalog.model"),
      render: (row) => (
        <span className="flex items-center gap-2">
          <span className="font-medium">{row.model}</span>
          {row.part_number && (
            <span className="font-mono text-xs text-muted">{row.part_number}</span>
          )}
        </span>
      ),
    },
    {
      key: "default_role",
      header: t("catalog.defaultRole"),
      width: "12rem",
      render: (row) => <span className="text-muted">{te("deviceRole", row.default_role)}</span>,
    },
    {
      key: "u_height",
      header: t("catalog.uHeight"),
      width: "6rem",
      align: "right",
      render: (row) => <span className="tabular-nums">{row.u_height}U</span>,
    },
    {
      key: "ports",
      header: t("network.interfaces"),
      width: "7rem",
      align: "right",
      render: (row) => (
        <span className="tabular-nums text-muted">
          {row.port_templates.reduce((acc, item) => acc + item.count, 0)}
        </span>
      ),
    },
    {
      key: "power",
      header: t("catalog.powerNameplate"),
      width: "9rem",
      align: "right",
      render: (row) => (
        <span className="tabular-nums text-muted">
          {row.power_nameplate_w ? `${row.power_nameplate_w} Вт` : "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      width: "3rem",
      align: "right",
      render: (row) => (
        <IconButton
          label={t("catalog.deleteModel")}
          onClick={(event) => {
            event.stopPropagation();
            setPendingDelete(row);
          }}
        >
          <Trash2 size={13} />
        </IconButton>
      ),
    },
  ];

  const hasFilters = Boolean(q || manufacturerId || role);

  return (
    <>
      <PageHeader
        title={t("catalog.title")}
        subtitle={t("catalog.subtitle")}
        actions={
          <>
            <Button icon={<Plus size={14} />} onClick={() => setManufacturerOpen(true)}>
              {t("catalog.addManufacturer")}
            </Button>
            <Button
              variant="primary"
              icon={<Plus size={14} />}
              disabled={!manufacturers?.length}
              onClick={() => setEditing({ id: null })}
            >
              {t("catalog.addModel")}
            </Button>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[16rem_1fr]">
        <Panel title={t("catalog.manufacturers")} bodyClassName="p-0">
          {!manufacturers?.length ? (
            <EmptyState title={t("app.empty")} />
          ) : (
            <ul className="divide-y divide-[rgb(var(--border))]/60">
              {manufacturers.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setManufacturerId(manufacturerId === item.id ? "" : item.id);
                      setOffset(0);
                    }}
                    className={`row-hover flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm ${
                      manufacturerId === item.id ? "bg-[rgb(var(--accent-soft))]" : ""
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">{item.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel bodyClassName="p-0">
          <div className="flex flex-wrap items-center gap-2 border-b border-app p-2.5">
            <Input
              value={q}
              placeholder={t("app.search")}
              className="w-56"
              onChange={(event) => {
                setQ(event.target.value);
                setOffset(0);
              }}
            />
            <Select
              value={role}
              placeholder={`${t("devices.role")}: ${t("app.all")}`}
              className="w-48"
              onChange={(event) => {
                setRole(event.target.value);
                setOffset(0);
              }}
              options={(meta?.device_roles ?? []).map((value) => ({
                value,
                label: te("deviceRole", value),
              }))}
            />
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                icon={<X size={13} />}
                onClick={() => {
                  setQ("");
                  setRole("");
                  setManufacturerId("");
                  setOffset(0);
                }}
              >
                {t("app.reset")}
              </Button>
            )}
            <span className="ml-auto text-xs text-muted tabular-nums">
              {t("app.total")}: {data?.total ?? 0}
            </span>
          </div>

          <DataTable
            columns={columns}
            rows={data?.items ?? []}
            rowKey={(row) => row.id}
            loading={isFetching}
            emptyTitle={t("app.empty")}
            emptyHint={t("catalog.empty")}
            onRowClick={(row) => setEditing({ id: row.id })}
          />

          <Pagination
            total={data?.total ?? 0}
            limit={PAGE_SIZE}
            offset={offset}
            onChange={setOffset}
            labels={{
              previous: t("app.previous"),
              next: t("app.next"),
              range: (from, to, total) => t("app.range", { from, to, total }),
            }}
          />
        </Panel>
      </div>

      <ManufacturerDialog open={manufacturerOpen} onClose={() => setManufacturerOpen(false)} />

      {editing && (
        <ModelDialog open model={editingModel} onClose={() => setEditing(null)} />
      )}

      <Dialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        width="sm"
        title={t("catalog.deleteModelConfirm")}
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>{t("app.cancel")}</Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => pendingDelete && remove.mutate(pendingDelete.id)}
            >
              {t("app.delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm">
          {pendingDelete?.manufacturer.name} {pendingDelete?.model}
        </p>
        <p className="mt-1 text-xs text-muted">{t("catalog.devicesOnModel")}</p>
      </Dialog>
    </>
  );
}
