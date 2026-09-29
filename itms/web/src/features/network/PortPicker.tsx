import { useState } from "react";

import { useI18n } from "@/i18n";
import { useDeviceInterfaces, useDevices } from "@/shared/api/queries";
import { useDebounced } from "@/shared/hooks";
import { Field, Input, Select } from "@/shared/ui/Field";

/** Логические интерфейсы кабелем не коммутируются — бэкенд их отклонит. */
const LOGICAL_TYPES = new Set(["VIRTUAL", "LAG", "VLAN_IF", "WIRELESS"]);

export function PortPicker({
  label,
  value,
  excludeInterfaceId,
  onChange,
}: {
  label: string;
  value: string;
  excludeInterfaceId?: string;
  onChange: (interfaceId: string) => void;
}) {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const debounced = useDebounced(search, 250);

  const { data: devices } = useDevices({ q: debounced || undefined, limit: 50, offset: 0 });
  const { data: interfaces } = useDeviceInterfaces(deviceId || undefined);

  const ports = (interfaces ?? []).filter(
    (item) => !LOGICAL_TYPES.has(item.interface_type) && item.id !== excludeInterfaceId,
  );

  return (
    <div className="flex flex-col gap-2 rounded border border-app p-2.5">
      <p className="text-xs font-medium">{label}</p>
      <Input
        value={search}
        placeholder={t("app.search")}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label={t("nav.devices")}>
          <Select
            value={deviceId}
            placeholder={t("network.selectTarget")}
            onChange={(event) => {
              setDeviceId(event.target.value);
              onChange("");
            }}
            options={(devices?.items ?? []).map((item) => ({
              value: item.id,
              label: item.code ? `${item.code} — ${item.name}` : item.name,
            }))}
          />
        </Field>
        <Field label={t("network.port")}>
          <Select
            value={value}
            placeholder={t("app.nothingSelected")}
            disabled={!deviceId}
            onChange={(event) => onChange(event.target.value)}
            options={ports.map((item) => ({
              value: item.id,
              label: item.connection
                ? `${item.name} → ${item.connection.peer?.ci_name ?? "—"}`
                : item.name,
              disabled: Boolean(item.connection),
            }))}
          />
        </Field>
      </div>
    </div>
  );
}
