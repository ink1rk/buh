import { useMemo, useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useLocations, useMeta } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Textarea } from "@/shared/ui/Field";
import { Select } from "@/shared/ui/Field";
import { toast } from "@/shared/ui/toast";

export function LocationDialog({
  open,
  parentId,
  onClose,
}: {
  open: boolean;
  parentId: string | null;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: locations } = useLocations();

  const [locationType, setLocationType] = useState("ROOM");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [parent, setParent] = useState(parentId ?? "");
  const [address, setAddress] = useState("");
  const [description, setDescription] = useState("");

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createLocation(body),
    [keys.locations, keys.locationTree, keys.dashboard],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setName("");
        setCode("");
        setAddress("");
        setDescription("");
        onClose();
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  // Родителя можно выбрать только среди типов, разрешённых для этого уровня иерархии.
  const parentOptions = useMemo(() => {
    const allowed = meta?.location_parents[locationType] ?? [];
    return (locations ?? [])
      .filter((location) => allowed.includes(location.location_type))
      .map((location) => ({ value: location.id, label: location.path }));
  }, [locations, meta, locationType]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("locations.create")}
      description={t("locations.hierarchyHint")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                name: name.trim(),
                location_type: locationType,
                parent_id: parent || null,
                code: code.trim() || null,
                address: address.trim() || null,
                description: description.trim() || null,
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("locations.type")} required>
          <Select
            value={locationType}
            onChange={(event) => {
              setLocationType(event.target.value);
              setParent("");
            }}
            options={(meta?.location_types ?? []).map((value) => ({
              value,
              label: te("locationType", value),
            }))}
          />
        </Field>

        <Field
          label={t("locations.parent")}
          hint={parentOptions.length ? undefined : t("locations.noParentNeeded")}
        >
          <Select
            value={parent}
            placeholder="—"
            disabled={!parentOptions.length}
            onChange={(event) => setParent(event.target.value)}
            options={parentOptions}
          />
        </Field>

        <Field label={t("ci.name")} required>
          <Input value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </Field>

        <Field label={t("ci.code")}>
          <Input value={code} onChange={(event) => setCode(event.target.value)} />
        </Field>

        <Field label={t("locations.address")}>
          <Input value={address} onChange={(event) => setAddress(event.target.value)} />
        </Field>

        <Field label={t("ci.description")}>
          <Textarea
            rows={2}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
      </div>
    </Dialog>
  );
}
