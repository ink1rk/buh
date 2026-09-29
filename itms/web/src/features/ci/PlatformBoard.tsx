import { useI18n } from "@/i18n";
import type { DevicePart } from "@/shared/api/types";
import { cn } from "@/shared/lib/cn";

interface SlotOwner {
  label: string;
}

function ownersOf(items: DevicePart[]): Map<string, SlotOwner> {
  const owners = new Map<string, SlotOwner>();
  for (const part of items) {
    const label = `${part.component.manufacturer.name} ${part.component.model}`;
    for (const slot of part.slots ?? []) owners.set(slot, { label });
  }
  return owners;
}

function ramBanks(names: string[]) {
  const order: string[] = [];
  const banks = new Map<string, { A: string[]; B: string[] }>();
  for (const name of names) {
    const slash = name.indexOf("/");
    const slot = slash === -1 ? name : name.slice(0, slash);
    const cpu = slash === -1 ? "CPU1" : name.slice(slash + 1);
    const bank = banks.get(cpu) ?? { A: [], B: [] };
    if (!banks.has(cpu)) {
      banks.set(cpu, bank);
      order.push(cpu);
    }
    bank[slot.startsWith("B") ? "B" : "A"].push(name);
  }
  return order.map((cpu) => ({ cpu, ...banks.get(cpu)! }));
}

function Socket({
  name,
  label,
  onClick,
}: {
  name: string;
  label: string | null;
  onClick: () => void;
}) {
  const filled = Boolean(label);
  return (
    <button
      type="button"
      title={label ?? name}
      onClick={onClick}
      className={cn(
        "flex h-[4.5rem] w-36 flex-col items-center justify-center rounded-md border px-2 text-center",
        filled
          ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent-soft))]"
          : "border-dashed border-app bg-[rgb(var(--surface))]",
      )}
    >
      <span className="font-mono text-[10px] tracking-wide text-muted">{name}</span>
      <span className={cn("mt-1 line-clamp-2 text-[11px] leading-tight", !label && "text-muted")}>
        {label ?? "—"}
      </span>
    </button>
  );
}

function Dimm({
  name,
  label,
  onClick,
}: {
  name: string;
  label: string | null;
  onClick: () => void;
}) {
  const filled = Boolean(label);
  return (
    <button
      type="button"
      title={label ? `${name}: ${label}` : name}
      onClick={onClick}
      className={cn(
        "h-12 w-3.5 rounded-sm border",
        filled
          ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent))]"
          : "border-dashed border-app bg-[rgb(var(--surface))]",
      )}
    />
  );
}

export function PlatformBoard({
  cpuNames,
  ramNames,
  items,
  onToggle,
}: {
  cpuNames: string[];
  ramNames: string[];
  items: DevicePart[];
  onToggle: (name: string) => void;
}) {
  const { t } = useI18n();
  const owners = ownersOf(items);
  if (cpuNames.length === 0 && ramNames.length === 0) return null;
  const banks = ramBanks(ramNames);

  return (
    <div
      className="mb-4 rounded-lg border border-app bg-[rgb(var(--surface-muted))] p-3"
      data-testid="platform-board"
    >
      <p className="text-sm font-medium">{t("devices.platform")}</p>
      <p className="mt-1 mb-3 text-xs text-muted">{t("devices.platformHint")}</p>
      {cpuNames.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 font-mono text-[10px] tracking-[0.14em] text-muted uppercase">
            {t("devices.cpuSockets")}
          </p>
          <div className="flex flex-wrap gap-2">
            {cpuNames.map((name) => (
              <Socket
                key={name}
                name={name}
                label={owners.get(name)?.label ?? null}
                onClick={() => onToggle(name)}
              />
            ))}
          </div>
        </div>
      )}
      {banks.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="font-mono text-[10px] tracking-[0.14em] text-muted uppercase">
            {t("devices.memoryBanks")}
          </p>
          {banks.map((bank) => (
            <div key={bank.cpu}>
              <p className="mb-1 font-mono text-[10px] text-muted">{bank.cpu}</p>
              {(["A", "B"] as const).map((side) =>
                bank[side].length === 0 ? null : (
                  <div key={side} className="mb-1 flex flex-wrap items-end gap-1">
                    <span className="w-4 font-mono text-[10px] text-muted">{side}</span>
                    {bank[side].map((name) => (
                      <Dimm
                        key={name}
                        name={name}
                        label={owners.get(name)?.label ?? null}
                        onClick={() => onToggle(name)}
                      />
                    ))}
                  </div>
                ),
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
