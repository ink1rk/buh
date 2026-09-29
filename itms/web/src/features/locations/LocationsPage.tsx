import { Archive, ChevronRight, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useI18n } from "@/i18n";
import type { Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useLocationTree,
  useLocations,
} from "@/shared/api/queries";
import type { LocationNode } from "@/shared/api/types";
import { cn } from "@/shared/lib/cn";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { EmptyState, KeyValue, PageHeader, Panel, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { ConfirmDialog } from "../provenance/ReasonField";
import { LocationDialog } from "./LocationDialog";

function TreeRow({
  node,
  selected,
  onSelect,
}: {
  node: LocationNode;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { te } = useI18n();
  const [open, setOpen] = useState(node.depth < 2);
  const hasChildren = node.children.length > 0;

  return (
    <li>
      <div
        className={cn(
          "flex items-center gap-1 rounded px-1 py-1 row-hover",
          selected === node.id && "bg-[rgb(var(--accent-soft))]",
        )}
        style={{ paddingLeft: `${node.depth * 0.9 + 0.25}rem` }}
      >
        <button
          type="button"
          aria-label={node.name}
          onClick={() => setOpen((value) => !value)}
          className={cn("shrink-0 text-muted", !hasChildren && "invisible")}
        >
          <ChevronRight size={13} className={cn("transition-transform", open && "rotate-90")} />
        </button>
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm"
        >
          <span className="truncate">{node.name}</span>
          <span className="shrink-0 text-[0.7rem] text-muted">
            {te("locationType", node.location_type)}
          </span>
        </button>
        {node.ci_count > 0 && (
          <span className="shrink-0 rounded surface-muted px-1 text-[0.7rem] tabular-nums text-muted">
            {node.ci_count}
          </span>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((child) => (
            <TreeRow key={child.id} node={child} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function LocationsPage() {
  const { t, te } = useI18n();
  const [params, setParams] = useSearchParams();
  const selected = params.get("location");
  const [createOpen, setCreateOpen] = useState(false);
  const [archiving, setArchiving] = useState(false);

  const { data: tree, isPending } = useLocationTree();
  const { data: flat } = useLocations();

  const current = flat?.find((location) => location.id === selected) ?? null;

  const archive = useApiMutation(
    (provenance: Provenance) => mutations.archiveLocation(selected ?? "", provenance),
    [keys.locations, keys.locationTree, keys.dashboard],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setArchiving(false);
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  return (
    <>
      <PageHeader
        title={t("locations.title")}
        subtitle={t("locations.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
            {t("locations.create")}
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Panel title={t("locations.title")} bodyClassName="p-2">
          {isPending ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : !tree?.length ? (
            <EmptyState title={t("app.empty")} hint={t("locations.hierarchyHint")} />
          ) : (
            <ul>
              {tree.map((node) => (
                <TreeRow
                  key={node.id}
                  node={node}
                  selected={selected}
                  onSelect={(id) => setParams({ location: id }, { replace: true })}
                />
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title={current?.name ?? t("app.nothingSelected")}
          actions={
            current &&
            !current.archived_at && (
              <Button size="sm" icon={<Archive size={13} />} onClick={() => setArchiving(true)}>
                {t("app.archive")}
              </Button>
            )
          }
        >
          {!current ? (
            <EmptyState title={t("app.nothingSelected")} hint={t("locations.selectHint")} />
          ) : (
            <div className="flex flex-col gap-3">
              <KeyValue
                items={[
                  { label: t("locations.type"), value: te("locationType", current.location_type) },
                  { label: t("ci.code"), value: current.code ?? "—" },
                  { label: t("locations.address"), value: current.address ?? "—" },
                  {
                    label: t("locations.area"),
                    value: current.area_m2 ? `${current.area_m2} м²` : "—",
                  },
                  { label: t("ci.description"), value: current.description ?? "—" },
                  {
                    label: t("app.total"),
                    value: <span className="font-mono text-xs">{current.path}</span>,
                  },
                ]}
              />
              {current.archived_at && <Badge tone="warn">{t("ci.archived")}</Badge>}
              <Link
                to={`/ci?location=${current.id}`}
                className="text-xs text-accent hover:underline"
              >
                {t("locations.showObjects")}
              </Link>
            </div>
          )}
        </Panel>
      </div>

      <LocationDialog
        open={createOpen}
        parentId={selected}
        onClose={() => setCreateOpen(false)}
      />

      <ConfirmDialog
        open={archiving}
        title={t("locations.archiveConfirm")}
        confirmLabel={t("app.archive")}
        pending={archive.isPending}
        onCancel={() => setArchiving(false)}
        onConfirm={(provenance) => archive.mutate(provenance)}
      />
    </>
  );
}
