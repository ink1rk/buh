import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useVirtualization } from "@/shared/api/queries";
import type { VirtVm } from "@/shared/api/types";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, PageHeader } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function memory(mb: number): string {
  if (mb >= 1024) return `${Math.round((mb / 1024) * 10) / 10} ГБ`;
  return `${mb} МБ`;
}

export function VmRegistryPage() {
  const { t, te } = useI18n();
  const { data, isLoading } = useVirtualization();
  const [query, setQuery] = useState("");
  const [hostId, setHostId] = useState("");
  const [open, setOpen] = useState(false);
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.vms ?? []).filter((vm) => {
      if (hostId && vm.host_id !== hostId) return false;
      if (!needle) return true;
      return `${vm.name} ${vm.host_name ?? ""} ${vm.guest_os ?? ""}`.toLowerCase().includes(needle);
    });
  }, [data, hostId, query]);
  const columns: Column<VirtVm>[] = [
    {
      key: "name",
      header: t("platform.name"),
      render: (row) => (
        <Link to={`/ci/${row.id}`} className="font-medium">
          {row.name}
        </Link>
      ),
    },
    { key: "host", header: t("platform.host"), render: (row) => row.host_name ?? "—" },
    { key: "cpu", header: "vCPU", render: (row) => <span className="tabular-nums">{row.vcpu}</span> },
    { key: "ram", header: t("platform.memory"), render: (row) => memory(row.memory_mb) },
    { key: "disk", header: t("platform.disk"), render: (row) => `${row.disk_gb} ГБ` },
    {
      key: "power",
      header: t("platform.powerState"),
      render: (row) => te("vmPowerState", row.power_state),
    },
  ];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("platform.vms")}
        subtitle={t("platform.vmsHint")}
        actions={
          <>
            <Button variant="primary" onClick={() => setOpen(true)}>
              {t("platform.addVm")}
            </Button>
            <Link to="/virtualization" className="text-sm text-[rgb(var(--accent))]">
              {t("platform.openVirt")}
            </Link>
          </>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          value={query}
          placeholder={t("app.search")}
          onChange={(event) => setQuery(event.target.value)}
          className="max-w-sm"
        />
        <Select
          value={hostId}
          placeholder={t("platform.allHosts")}
          onChange={(event) => setHostId(event.target.value)}
          options={(data?.hosts ?? []).map((item) => ({ value: item.id, label: item.name }))}
          className="max-w-xs"
        />
      </div>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={isLoading}
        emptyTitle={t("app.empty")}
      />
      <VmDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function VmDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const { data } = useVirtualization();
  const [name, setName] = useState("");
  const [hostId, setHostId] = useState("");
  const [vcpu, setVcpu] = useState("2");
  const [memoryMb, setMemoryMb] = useState("4096");
  const [disk, setDisk] = useState("40");
  const [guest, setGuest] = useState("");
  const [power, setPower] = useState("RUNNING");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation(
    (body: Record<string, unknown>) => mutations.createVm(body),
    [keys.virtualization, keys.platform],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setName("");
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
      title={t("platform.addVm")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || save.isPending}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                host_id: hostId || null,
                vcpu: Math.max(1, Number(vcpu) || 1),
                memory_mb: Math.max(1, Number(memoryMb) || 1),
                disk_gb: Math.max(0, Number(disk) || 0),
                guest_os: guest.trim() || null,
                power_state: power,
              })
            }
          >
            {t("app.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("platform.name")} required>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("platform.host")}>
          <Select
            value={hostId}
            placeholder="—"
            onChange={(event) => setHostId(event.target.value)}
            options={(data?.hosts ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="vCPU">
            <Input value={vcpu} onChange={(event) => setVcpu(event.target.value)} />
          </Field>
          <Field label={t("platform.memoryMb")}>
            <Input value={memoryMb} onChange={(event) => setMemoryMb(event.target.value)} />
          </Field>
          <Field label={t("platform.diskGb")}>
            <Input value={disk} onChange={(event) => setDisk(event.target.value)} />
          </Field>
        </div>
        <Field label={t("platform.guest")}>
          <Input value={guest} onChange={(event) => setGuest(event.target.value)} />
        </Field>
        <Field label={t("platform.powerState")}>
          <Select
            value={power}
            onChange={(event) => setPower(event.target.value)}
            options={["RUNNING", "STOPPED", "SUSPENDED"].map((value) => ({
              value,
              label: te("vmPower", value),
            }))}
          />
        </Field>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}
