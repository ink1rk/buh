import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { mutations, useApiMutation, useVlans } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input } from "@/shared/ui/Field";
import { FormError, PageHeader } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";
import type { VlanRow } from "@/shared/api/types";

export function VlanRegistryPage() {
  const { t } = useI18n();
  const { data, isLoading } = useVlans({});
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const items = data ?? [];
    if (!needle) return items;
    return items.filter((item) =>
      `${item.vid} ${item.name} ${item.purpose ?? ""} ${item.site_name ?? ""}`
        .toLowerCase()
        .includes(needle),
    );
  }, [data, query]);
  const columns: Column<VlanRow>[] = [
    { key: "vid", header: "VLAN", render: (row) => <span className="font-mono tabular-nums">{row.vid}</span> },
    { key: "name", header: t("platform.name"), render: (row) => row.name },
    { key: "purpose", header: t("platform.purpose"), render: (row) => row.purpose ?? "—" },
    { key: "site", header: t("platform.site"), render: (row) => row.site_name ?? "—" },
    {
      key: "prefixes",
      header: t("platform.prefixes"),
      render: (row) => <span className="tabular-nums">{row.prefix_count}</span>,
    },
  ];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("platform.vlans")}
        subtitle={t("platform.vlansHint")}
        actions={
          <>
            <Button variant="primary" onClick={() => setOpen(true)}>
              {t("platform.addVlan")}
            </Button>
            <Link to="/ipam" className="text-sm text-[rgb(var(--accent))]">
              {t("platform.openIpam")}
            </Link>
          </>
        }
      />
      <Input
        value={query}
        placeholder={t("app.search")}
        onChange={(event) => setQuery(event.target.value)}
        className="max-w-sm"
      />
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={isLoading}
        emptyTitle={t("app.empty")}
      />
      <VlanDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function VlanDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const [vid, setVid] = useState("");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation(
    (body: Record<string, unknown>) => mutations.createVlan(body),
    [["ipam", "vlans"], ["platform"]],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setVid("");
        setName("");
        setPurpose("");
        setError(null);
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  const number = Number(vid);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("platform.addVlan")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || !Number.isInteger(number) || number < 1 || number > 4094 || save.isPending}
            onClick={() =>
              save.mutate({
                vid: number,
                name: name.trim(),
                purpose: purpose.trim() || null,
              })
            }
          >
            {t("app.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="VLAN" required>
          <Input value={vid} onChange={(event) => setVid(event.target.value)} />
        </Field>
        <Field label={t("platform.name")} required>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("platform.purpose")}>
          <Input value={purpose} onChange={(event) => setPurpose(event.target.value)} />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
