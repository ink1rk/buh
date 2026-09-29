import { useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useCiList, useMeta } from "@/shared/api/queries";
import { useDebounced } from "@/shared/hooks";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select, Textarea } from "@/shared/ui/Field";
import { toast } from "@/shared/ui/toast";

export function RelationDialog({
  open,
  sourceCiId,
  onClose,
}: {
  open: boolean;
  sourceCiId: string;
  onClose: () => void;
}) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const [search, setSearch] = useState("");
  const [targetId, setTargetId] = useState("");
  const [relType, setRelType] = useState("DEPENDS_ON");
  const [description, setDescription] = useState("");
  const debounced = useDebounced(search, 250);

  const { data: candidates } = useCiList({ q: debounced || undefined, limit: 25, offset: 0 });

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createRelation(body),
    [keys.ciRelated(sourceCiId), keys.ciHistory(sourceCiId)],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setTargetId("");
        setSearch("");
        setDescription("");
        onClose();
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const options = (candidates?.items ?? [])
    .filter((item) => item.id !== sourceCiId)
    .map((item) => ({
      value: item.id,
      label: item.code ? `${item.code} — ${item.name}` : item.name,
    }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("ci.addRelation")}
      description={t("ci.relationHint")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!targetId || create.isPending}
            onClick={() =>
              create.mutate({
                source_ci_id: sourceCiId,
                target_ci_id: targetId,
                rel_type: relType,
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
        <Field label={t("ci.relationType")}>
          <Select
            value={relType}
            onChange={(event) => setRelType(event.target.value)}
            options={(meta?.relation_types ?? []).map((value) => ({
              value,
              label: te("relationType", value),
            }))}
          />
        </Field>

        <Field label={t("app.search")}>
          <Input
            value={search}
            autoFocus
            placeholder={t("ci.searchTarget")}
            onChange={(event) => setSearch(event.target.value)}
          />
        </Field>

        <Field label={t("ci.relationTarget")} required>
          <Select
            value={targetId}
            placeholder={t("app.nothingSelected")}
            onChange={(event) => setTargetId(event.target.value)}
            options={options}
            size={8}
            className="h-40"
          />
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
