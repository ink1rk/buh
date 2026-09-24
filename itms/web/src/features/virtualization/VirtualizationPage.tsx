import { Cpu, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useVirtualization } from "@/shared/api/queries";
import type { Provenance } from "@/shared/api/client";
import type { VirtHost, VirtOverview, VirtVm } from "@/shared/api/types";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { EmptyState, FormError, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";
import { cn } from "@/shared/lib/cn";

const PLATFORMS = ["PROXMOX", "VMWARE", "HYPERV", "KVM", "OTHER"] as const;
const POWER_STATES = ["RUNNING", "STOPPED", "SUSPENDED"] as const;
const HOST_KINDS = ["CLUSTER", "DEVICE"] as const;
const REFRESH = [keys.virtualization, ["ci"], keys.dashboard] as const;

function formatMem(mb: number): string {
  if (mb >= 1024) {
    const gb = mb / 1024;
    const digits = Number.isInteger(gb) ? 0 : 1;
    return `${gb.toLocaleString("ru-RU", {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    })} ГБ`;
  }
  return `${mb.toLocaleString("ru-RU")} МБ`;
}

function formatGb(gb: number): string {
  return `${gb.toLocaleString("ru-RU")} ГБ`;
}

function whole(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  return Number(value);
}

function cpuOver(host: VirtHost): boolean {
  if (host.cpu_cores <= 0) return host.vcpu_running > 0 || host.vcpu_allocated > 0;
  return host.vcpu_running > host.cpu_cores || host.vcpu_allocated > host.cpu_cores;
}

function ramOver(host: VirtHost): boolean {
  if (host.memory_mb <= 0) return host.memory_running_mb > 0 || host.memory_allocated_mb > 0;
  return host.memory_running_mb > host.memory_mb || host.memory_allocated_mb > host.memory_mb;
}

function diskOver(host: VirtHost): boolean {
  if (host.storage_gb <= 0) return host.disk_allocated_gb > 0;
  return host.disk_allocated_gb > host.storage_gb;
}

function hostOver(host: VirtHost): boolean {
  return cpuOver(host) || ramOver(host) || diskOver(host);
}

function Meter({
  label,
  usedLabel,
  capacityLabel,
  ratio,
  over,
  extra,
}: {
  label: string;
  usedLabel: string;
  capacityLabel: string;
  ratio: number;
  over: boolean;
  extra?: string;
}) {
  const width = Math.max(0, Math.min(100, ratio));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-[11px]">
        <span className="text-muted">{label}</span>
        <span className={cn("tabular-nums", over && "text-[rgb(var(--danger))]")}>
          {usedLabel} / {capacityLabel}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[rgb(var(--bg))]">
        <div
          className={cn("h-full rounded-full", over ? "bg-[rgb(var(--danger))]" : "bg-[rgb(var(--accent))]")}
          style={{ width: `${width}%` }}
        />
      </div>
      {extra && <p className="mt-1 text-[11px] text-muted">{extra}</p>}
    </div>
  );
}

function ratio(used: number, capacity: number): number {
  if (capacity <= 0) return used > 0 ? 100 : 0;
  return (used / capacity) * 100;
}

function HostDialog({
  host,
  onClose,
}: {
  host: VirtHost | null;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const [name, setName] = useState(host?.name ?? "");
  const [code, setCode] = useState(host?.code ?? "");
  const [kind, setKind] = useState(host?.ci_type ?? "CLUSTER");
  const [platform, setPlatform] = useState(host?.platform ?? "PROXMOX");
  const [cpu, setCpu] = useState(String(host?.cpu_cores ?? 8));
  const [memory, setMemory] = useState(String(host?.memory_mb ?? 16384));
  const [disk, setDisk] = useState(String(host?.storage_gb ?? 500));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation(
    (input: { body: Record<string, unknown>; provenance?: Provenance }) =>
      host
        ? mutations.updateHost(host.id, input.body, input.provenance)
        : mutations.createHost(input.body),
    [...REFRESH],
    {
      onSuccess: () => {
        toast.success(host ? t("app.saved") : t("app.created"));
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  const archive = useApiMutation(() => mutations.archiveCi(host?.id ?? ""), [...REFRESH], {
    onSuccess: () => {
      toast.success(t("virtualization.archived"));
      onClose();
    },
    onError: (err) => setError(describeError(err, t)),
  });
  const submit = () => {
    const cores = whole(cpu);
    const memoryMb = whole(memory);
    const storageGb = whole(disk);
    if (!name.trim() || cores == null || memoryMb == null || storageGb == null) {
      setError(t("app.error"));
      return;
    }
    if (host && !reason.trim()) {
      setError(t("app.reason"));
      return;
    }
    save.mutate({
      body: {
        name: name.trim(),
        code: code.trim() || null,
        ci_type: kind,
        platform,
        cpu_cores: cores,
        memory_mb: memoryMb,
        storage_gb: storageGb,
      },
      provenance: host ? { reason: reason.trim() } : undefined,
    });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      width="sm"
      title={host ? t("virtualization.editHost") : t("virtualization.createHost")}
      footer={
        <>
          {host && (
            <Button variant="danger" disabled={archive.isPending} onClick={() => archive.mutate()}>
              {t("app.archive")}
            </Button>
          )}
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            data-testid="virt-host-save"
            disabled={!name.trim() || save.isPending}
            onClick={submit}
          >
            {host ? t("app.save") : t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("virtualization.name")} required htmlFor="virt-host-name">
          <Input id="virt-host-name" value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("virtualization.code")} htmlFor="virt-host-code">
          <Input id="virt-host-code" value={code} onChange={(event) => setCode(event.target.value)} />
        </Field>
        {!host && (
          <Field label={t("virtualization.kind")} htmlFor="virt-host-kind">
            <Select
              id="virt-host-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              options={HOST_KINDS.map((item) => ({ value: item, label: te("ciType", item) }))}
            />
          </Field>
        )}
        <Field label={t("virtualization.platform")} htmlFor="virt-host-platform">
          <Select
            id="virt-host-platform"
            value={platform}
            onChange={(event) => setPlatform(event.target.value)}
            options={PLATFORMS.map((item) => ({ value: item, label: te("hypervisorPlatform", item) }))}
          />
        </Field>
        <Field label={t("virtualization.cpuCores")} htmlFor="virt-host-cpu">
          <Input id="virt-host-cpu" inputMode="numeric" value={cpu} onChange={(event) => setCpu(event.target.value)} />
        </Field>
        <Field label={t("virtualization.memoryMb")} htmlFor="virt-host-memory">
          <Input
            id="virt-host-memory"
            inputMode="numeric"
            value={memory}
            onChange={(event) => setMemory(event.target.value)}
          />
        </Field>
        <Field label={t("virtualization.storageGb")} htmlFor="virt-host-disk">
          <Input id="virt-host-disk" inputMode="numeric" value={disk} onChange={(event) => setDisk(event.target.value)} />
        </Field>
        {host && (
          <Field label={t("app.reason")} required htmlFor="virt-host-reason">
            <Input id="virt-host-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
        )}
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function VmDialog({
  vm,
  hosts,
  onClose,
}: {
  vm: VirtVm | null;
  hosts: VirtHost[];
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const [name, setName] = useState(vm?.name ?? "");
  const [code, setCode] = useState(vm?.code ?? "");
  const [hostId, setHostId] = useState(vm?.host_id ?? hosts[0]?.id ?? "");
  const [vcpu, setVcpu] = useState(String(vm?.vcpu ?? 2));
  const [memory, setMemory] = useState(String(vm?.memory_mb ?? 2048));
  const [disk, setDisk] = useState(String(vm?.disk_gb ?? 40));
  const [guestOs, setGuestOs] = useState(vm?.guest_os ?? "");
  const [powerState, setPowerState] = useState(vm?.power_state ?? "RUNNING");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation(
    (input: { body: Record<string, unknown>; provenance?: Provenance }) =>
      vm ? mutations.updateVm(vm.id, input.body, input.provenance) : mutations.createVm(input.body),
    [...REFRESH],
    {
      onSuccess: () => {
        toast.success(vm ? t("app.saved") : t("app.created"));
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  const archive = useApiMutation(() => mutations.archiveCi(vm?.id ?? ""), [...REFRESH], {
    onSuccess: () => {
      toast.success(t("virtualization.archived"));
      onClose();
    },
    onError: (err) => setError(describeError(err, t)),
  });
  const submit = () => {
    const cores = whole(vcpu);
    const memoryMb = whole(memory);
    const diskGb = whole(disk);
    if (!name.trim() || cores == null || cores < 1 || memoryMb == null || memoryMb < 1 || diskGb == null) {
      setError(t("app.error"));
      return;
    }
    if (vm && !reason.trim()) {
      setError(t("app.reason"));
      return;
    }
    save.mutate({
      body: {
        name: name.trim(),
        code: code.trim() || null,
        host_id: hostId || null,
        vcpu: cores,
        memory_mb: memoryMb,
        disk_gb: diskGb,
        guest_os: guestOs.trim() || null,
        power_state: powerState,
      },
      provenance: vm ? { reason: reason.trim() } : undefined,
    });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      width="sm"
      title={vm ? t("virtualization.editVm") : t("virtualization.createVm")}
      footer={
        <>
          {vm && (
            <Button variant="danger" disabled={archive.isPending} onClick={() => archive.mutate()}>
              {t("app.archive")}
            </Button>
          )}
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            data-testid="virt-vm-save"
            disabled={!name.trim() || save.isPending}
            onClick={submit}
          >
            {vm ? t("app.save") : t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("virtualization.name")} required htmlFor="virt-vm-name">
          <Input id="virt-vm-name" value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label={t("virtualization.code")} htmlFor="virt-vm-code">
          <Input id="virt-vm-code" value={code} onChange={(event) => setCode(event.target.value)} />
        </Field>
        <Field label={t("virtualization.host")} htmlFor="virt-vm-host">
          <Select
            id="virt-vm-host"
            value={hostId}
            placeholder={t("virtualization.noHost")}
            onChange={(event) => setHostId(event.target.value)}
            options={hosts.map((item) => ({
              value: item.id,
              label: item.code ? `${item.name} · ${item.code}` : item.name,
            }))}
          />
        </Field>
        <Field label={t("virtualization.vcpu")} htmlFor="virt-vm-vcpu">
          <Input id="virt-vm-vcpu" inputMode="numeric" value={vcpu} onChange={(event) => setVcpu(event.target.value)} />
        </Field>
        <Field label={t("virtualization.memoryMb")} htmlFor="virt-vm-memory">
          <Input
            id="virt-vm-memory"
            inputMode="numeric"
            value={memory}
            onChange={(event) => setMemory(event.target.value)}
          />
        </Field>
        <Field label={t("virtualization.diskGb")} htmlFor="virt-vm-disk">
          <Input id="virt-vm-disk" inputMode="numeric" value={disk} onChange={(event) => setDisk(event.target.value)} />
        </Field>
        <Field label={t("virtualization.guestOs")} htmlFor="virt-vm-os">
          <Input id="virt-vm-os" value={guestOs} onChange={(event) => setGuestOs(event.target.value)} />
        </Field>
        <Field label={t("virtualization.powerState")} htmlFor="virt-vm-state">
          <Select
            id="virt-vm-state"
            value={powerState}
            onChange={(event) => setPowerState(event.target.value)}
            options={POWER_STATES.map((item) => ({ value: item, label: te("vmPowerState", item) }))}
          />
        </Field>
        {vm && (
          <Field label={t("app.reason")} required htmlFor="virt-vm-reason">
            <Input id="virt-vm-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
        )}
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function SummaryFigure({
  label,
  value,
  testId,
  danger,
}: {
  label: string;
  value: string;
  testId: string;
  danger?: boolean;
}) {
  return (
    <div className="card px-4 py-3">
      <div className="text-[11px] tracking-wide text-muted uppercase">{label}</div>
      <div
        className={cn(
          "mt-1 text-3xl font-semibold tabular-nums tracking-tight",
          danger && "text-[rgb(var(--danger))]",
        )}
        data-testid={testId}
      >
        {value}
      </div>
    </div>
  );
}

function HostCard({ host, onEdit }: { host: VirtHost; onEdit: () => void }) {
  const { t, te } = useI18n();
  const over = hostOver(host);
  const cpuAllocated =
    host.vcpu_allocated !== host.vcpu_running
      ? t("virtualization.allocated", { value: host.vcpu_allocated })
      : undefined;
  const ramAllocated =
    host.memory_allocated_mb !== host.memory_running_mb
      ? t("virtualization.allocated", { value: formatMem(host.memory_allocated_mb) })
      : undefined;
  return (
    <article
      className="card flex flex-col gap-4 p-4"
      data-testid="virt-host"
      data-code={host.code ?? ""}
      data-overcommit={over ? "true" : "false"}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Badge tone="accent">{te("hypervisorPlatform", host.platform)}</Badge>
            {over && <Badge tone="danger">{t("virtualization.overcommit")}</Badge>}
          </div>
          <Link to={`/ci/${host.id}`} className="mt-2 block text-sm font-semibold tracking-tight hover:underline">
            {host.name}
          </Link>
          {host.code && <div className="font-mono text-[11px] text-muted">{host.code}</div>}
        </div>
        <Button size="sm" onClick={onEdit}>
          {t("app.edit")}
        </Button>
      </header>
      <div>
        <div
          className={cn(
            "text-5xl font-semibold tabular-nums tracking-tight",
            cpuOver(host) && "text-[rgb(var(--danger))]",
          )}
        >
          {host.vcpu_running}
        </div>
        <p className="text-[11px] text-muted">
          {t("virtualization.vcpu")} {t("virtualization.ofCapacity", { value: host.cpu_cores })}
        </p>
        <p className="mt-1 text-[12px] text-muted">
          {t("virtualization.vmLine", { running: host.vm_running, count: host.vm_count })}
        </p>
      </div>
      <div className="flex flex-col gap-3">
        <Meter
          label={t("virtualization.vcpu")}
          usedLabel={String(host.vcpu_running)}
          capacityLabel={String(host.cpu_cores)}
          ratio={ratio(host.vcpu_running, host.cpu_cores)}
          over={cpuOver(host)}
          extra={cpuAllocated}
        />
        <Meter
          label={t("virtualization.memory")}
          usedLabel={formatMem(host.memory_running_mb)}
          capacityLabel={formatMem(host.memory_mb)}
          ratio={ratio(host.memory_running_mb, host.memory_mb)}
          over={ramOver(host)}
          extra={ramAllocated}
        />
        <Meter
          label={t("virtualization.disk")}
          usedLabel={formatGb(host.disk_allocated_gb)}
          capacityLabel={formatGb(host.storage_gb)}
          ratio={ratio(host.disk_allocated_gb, host.storage_gb)}
          over={diskOver(host)}
        />
      </div>
    </article>
  );
}

export function VirtualizationPage() {
  const { t, te } = useI18n();
  const query = useVirtualization();
  const overview: VirtOverview | undefined = query.data;
  const [hostDraft, setHostDraft] = useState<VirtHost | "new" | null>(null);
  const [vmDraft, setVmDraft] = useState<VirtVm | "new" | null>(null);
  const totals = overview?.totals;
  const hasRows = Boolean(overview && (overview.hosts.length > 0 || overview.vms.length > 0));
  const fleetOver = Boolean(
    totals &&
      ((totals.cpu_cores > 0 && totals.vcpu_running > totals.cpu_cores) ||
        (totals.memory_mb > 0 && totals.memory_running_mb > totals.memory_mb) ||
        (totals.storage_gb > 0 && totals.disk_allocated_gb > totals.storage_gb)),
  );

  return (
    <div data-testid="virtualization-page" className="flex flex-col gap-4">
      <PageHeader
        title={t("virtualization.title")}
        subtitle={t("virtualization.subtitle")}
        actions={
          <>
            <Button data-testid="virt-add-host" icon={<Plus size={16} />} onClick={() => setHostDraft("new")}>
              {t("virtualization.createHost")}
            </Button>
            <Button
              data-testid="virt-add-vm"
              variant="primary"
              icon={<Plus size={16} />}
              onClick={() => setVmDraft("new")}
            >
              {t("virtualization.createVm")}
            </Button>
          </>
        }
      />
      {query.isError && <FormError message={describeError(query.error, t)} />}
      {hasRows && totals && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryFigure
            label={t("virtualization.vms")}
            value={String(totals.vms)}
            testId="virt-vms"
          />
          <SummaryFigure
            label={t("virtualization.running")}
            value={String(totals.running)}
            testId="virt-running"
          />
          <SummaryFigure
            label={t("virtualization.vcpu")}
            value={`${totals.vcpu_running} / ${totals.cpu_cores}`}
            testId="virt-vcpu"
            danger={fleetOver && totals.vcpu_running > totals.cpu_cores}
          />
          <SummaryFigure
            label={t("virtualization.memory")}
            value={formatMem(totals.memory_running_mb)}
            testId="virt-memory"
            danger={fleetOver && totals.memory_running_mb > totals.memory_mb}
          />
        </div>
      )}
      {overview && overview.hosts.length > 0 && (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {overview.hosts.map((host) => (
            <HostCard key={host.id} host={host} onEdit={() => setHostDraft(host)} />
          ))}
        </section>
      )}
      {overview && overview.vms.length > 0 && (
        <Panel
          title={t("virtualization.vms")}
          actions={
            <span className="inline-flex items-center gap-1 text-xs text-muted">
              <Cpu size={14} />
              <span data-testid="virt-disk">{formatGb(totals?.disk_allocated_gb ?? 0)}</span>
            </span>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="px-2 py-1">{t("virtualization.name")}</th>
                  <th className="px-2 py-1">{t("virtualization.host")}</th>
                  <th className="px-2 py-1">{t("virtualization.vcpu")}</th>
                  <th className="px-2 py-1">{t("virtualization.memory")}</th>
                  <th className="px-2 py-1">{t("virtualization.disk")}</th>
                  <th className="px-2 py-1">{t("virtualization.powerState")}</th>
                  <th className="px-2 py-1" />
                </tr>
              </thead>
              <tbody>
                {overview.vms.map((vm) => (
                  <tr key={vm.id} data-testid="virt-vm" data-code={vm.code ?? ""}>
                    <td className="px-2 py-1.5">
                      <Link to={`/ci/${vm.id}`} className="font-medium hover:underline">
                        {vm.name}
                      </Link>
                      <div className="text-xs text-muted">
                        {vm.code}
                        {vm.guest_os ? ` · ${vm.guest_os}` : ""}
                      </div>
                    </td>
                    <td className="px-2 py-1.5">
                      {vm.host_name ?? t("virtualization.noHost")}
                      {vm.host_code && (
                        <div className="font-mono text-[11px] text-muted">{vm.host_code}</div>
                      )}
                    </td>
                    <td className="px-2 py-1.5 tabular-nums">{vm.vcpu}</td>
                    <td className="px-2 py-1.5 tabular-nums">{formatMem(vm.memory_mb)}</td>
                    <td className="px-2 py-1.5 tabular-nums">{formatGb(vm.disk_gb)}</td>
                    <td className="px-2 py-1.5">
                      <Badge tone={vm.power_state === "RUNNING" ? "ok" : "neutral"}>
                        {te("vmPowerState", vm.power_state)}
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <Button size="sm" onClick={() => setVmDraft(vm)}>
                        {t("app.edit")}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      {overview && !hasRows && (
        <Panel>
          <EmptyState title={t("virtualization.empty")} hint={t("virtualization.emptyHint")} />
        </Panel>
      )}
      {hostDraft && (
        <HostDialog host={hostDraft === "new" ? null : hostDraft} onClose={() => setHostDraft(null)} />
      )}
      {vmDraft && overview && (
        <VmDialog
          vm={vmDraft === "new" ? null : vmDraft}
          hosts={overview.hosts}
          onClose={() => setVmDraft(null)}
        />
      )}
    </div>
  );
}
