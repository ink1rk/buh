import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type ColorMode,
} from "@xyflow/react";
import { Download, Plus, RefreshCw, Save, Trash2, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useI18n } from "@/i18n";
import { ApiError } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useCiList,
  useDiagram,
} from "@/shared/api/queries";
import type { DiagramFull } from "@/shared/api/types";
import { useDebounced } from "@/shared/hooks";
import { useUiStore } from "@/shared/store/ui";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input } from "@/shared/ui/Field";
import { EmptyState, FormError, PageHeader, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

import { diagramEdgeTypes, diagramNodeTypes } from "./DiagramNodes";
import {
  diagramToSvg,
  downloadSvg,
  retargetEdges,
  toFlow,
  type FlowEdge,
  type FlowNode,
} from "./diagramView";

import "@xyflow/react/dist/style.css";

function AddNodeDialog({
  diagramId,
  diagramType,
  present,
  onClose,
  onBeforeAdd,
  onAdded,
}: {
  diagramId: string;
  diagramType: string;
  present: Set<string>;
  onClose: () => void;
  onBeforeAdd: () => Promise<boolean>;
  onAdded: () => Promise<void>;
}) {
  const { t, te } = useI18n();
  const [q, setQ] = useState("");
  const query = useDebounced(q, 200);
  const [error, setError] = useState<string | null>(null);
  const list = useCiList({
    q: query,
    ci_type:
      diagramType === "NETWORK" ? ["DEVICE"] : diagramType === "POWER" ? ["POWER_NODE"] : undefined,
    limit: 20,
    offset: 0,
  });
  const add = useApiMutation(
    (ciId: string) => mutations.addDiagramNode(diagramId, ciId),
    [keys.diagram(diagramId)],
    {
      onSuccess: async () => {
        await onAdded();
        toast.success(t("app.saved"));
        onClose();
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  return (
    <Dialog open onClose={onClose} width="sm" title={t("diagrams.addNode")}>
      <div className="flex flex-col gap-2">
        <Field label={t("diagrams.searchObject")} htmlFor="diagram-node-search">
          <Input
            id="diagram-node-search"
            value={q}
            autoFocus
            onChange={(event) => setQ(event.target.value)}
          />
        </Field>
        <ul className="max-h-72 overflow-y-auto">
          {(list.data?.items ?? []).map((item) => {
            const taken = present.has(item.id);
            return (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={taken || add.isPending}
                  className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-[rgb(var(--surface-muted))] disabled:opacity-50"
                  onClick={() => {
                    void onBeforeAdd().then((ok) => {
                      if (ok) add.mutate(item.id);
                    });
                  }}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{item.name}</span>
                    <span className="block truncate font-mono text-[11px] text-muted">
                      {item.code ?? te("ciType", item.ci_type)}
                    </span>
                  </span>
                  {taken && <span className="shrink-0 text-xs text-muted">{t("diagrams.alreadyOnDiagram")}</span>}
                </button>
              </li>
            );
          })}
          {list.data && list.data.items.length === 0 && (
            <li className="px-2 py-3 text-sm text-muted">{t("diagrams.noMatches")}</li>
          )}
        </ul>
        <FormError message={error} />
      </div>
    </Dialog>
  );
}

function Editor({ diagramId }: { diagramId: string }) {
  const { t, te } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const theme = useUiStore((state) => state.theme);
  const { data, isLoading, error, refetch } = useDiagram(diagramId);
  const { fitView, getNodes, getEdges, getViewport } = useReactFlow<FlowNode, FlowEdge>();
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>([]);
  const [dirty, setDirty] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const applied = useRef<number | null>(null);
  const fitted = useRef(false);

  useEffect(() => {
    if (!data || dirty) return;
    if (applied.current === data.diagram.version) return;
    const flow = toFlow(data.nodes, data.edges);
    setNodes(flow.nodes);
    setEdges(flow.edges);
    applied.current = data.diagram.version;
    if (!fitted.current && flow.nodes.length > 0 && !data.diagram.viewport.zoom) {
      fitted.current = true;
      requestAnimationFrame(() => fitView({ padding: 0.2 }));
    }
  }, [data, dirty, fitView, setEdges, setNodes]);

  const publish = (full: DiagramFull) => {
    queryClient.setQueryData(keys.diagram(diagramId), full);
    setDirty(false);
    setConflict(false);
  };

  const persist = async (): Promise<boolean> => {
    if (!data) return false;
    const current = getNodes();
    try {
      const saved = await mutations.saveDiagramLayout(diagramId, {
        version: data.diagram.version,
        nodes: current.map((node) => ({ id: node.id, x: node.position.x, y: node.position.y })),
        viewport: getViewport(),
      });
      queryClient.setQueryData<DiagramFull>(keys.diagram(diagramId), (currentData) => {
        if (!currentData) return currentData;
        const positions = new Map(current.map((node) => [node.id, node.position]));
        return {
          ...currentData,
          diagram: { ...saved, viewport: getViewport() },
          nodes: currentData.nodes.map((node) => {
            const position = positions.get(node.id);
            return position ? { ...node, x: position.x, y: position.y } : node;
          }),
        };
      });
      setDirty(false);
      setConflict(false);
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.code === "version_conflict") setConflict(true);
      setErrorText(describeError(err, t));
      return false;
    }
  };

  const save = useApiMutation(async () => {
    const ok = await persist();
    if (!ok) throw new Error("layout");
  }, [], {
    onSuccess: () => {
      setErrorText(null);
      toast.success(t("app.saved"));
    },
  });

  const layout = useApiMutation(() => mutations.autolayoutDiagram(diagramId), [], {
    onSuccess: (full) => {
      publish(full);
      toast.success(t("diagrams.laidOut"));
      requestAnimationFrame(() => fitView({ padding: 0.2 }));
    },
    onError: (err) => setErrorText(describeError(err, t)),
  });

  const sync = useApiMutation(
    async () => {
      if (dirty) {
        const ok = await persist();
        if (!ok) throw new Error("layout");
      }
      return mutations.syncDiagram(diagramId);
    },
    [],
    {
      onSuccess: (full) => {
        publish(full);
        toast.success(t("diagrams.synced"));
      },
      onError: (err) => {
        if (!(err instanceof Error && err.message === "layout")) setErrorText(describeError(err, t));
      },
    },
  );

  const removeNode = useApiMutation(
    async (nodeId: string) => {
      if (dirty) {
        const ok = await persist();
        if (!ok) throw new Error("layout");
      }
      await mutations.removeDiagramNode(nodeId);
    },
    [keys.diagram(diagramId)],
    {
      onSuccess: async () => {
        setSelectedId(null);
        setDirty(false);
        await refetch();
        toast.success(t("diagrams.removed"));
      },
      onError: (err) => {
        if (!(err instanceof Error && err.message === "layout")) setErrorText(describeError(err, t));
      },
    },
  );

  const removeDiagram = useApiMutation(() => mutations.deleteDiagram(diagramId), [keys.diagrams], {
    onSuccess: () => navigate("/diagrams"),
    onError: (err) => setErrorText(describeError(err, t)),
  });

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!data) {
    return (
      <EmptyState
        title={t("errors.not_found")}
        hint={error ? describeError(error, t) : undefined}
        action={
          <Link to="/diagrams" className="text-accent hover:underline">
            {t("diagrams.title")}
          </Link>
        }
      />
    );
  }

  const selected = nodes.find((node) => node.id === selectedId);
  const colorMode: ColorMode = theme === "system" ? "system" : theme;
  const present = new Set(data.nodes.map((node) => node.ci_id).filter((id): id is string => Boolean(id)));

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] flex-col gap-3" data-testid="diagram-editor">
      <PageHeader
        title={data.diagram.name}
        subtitle={`${te("diagramType", data.diagram.diagram_type)} · ${t("diagrams.version", { version: data.diagram.version })}${dirty ? ` · ${t("diagrams.dirty")}` : ""}`}
        actions={
          <>
            <Button icon={<Plus size={14} />} onClick={() => setAdding(true)}>
              {t("diagrams.addNode")}
            </Button>
            <Button
              icon={<Trash2 size={14} />}
              disabled={!selected}
              onClick={() => selected && removeNode.mutate(selected.id)}
            >
              {t("diagrams.removeNode")}
            </Button>
            <Button icon={<RefreshCw size={14} />} disabled={sync.isPending} onClick={() => sync.mutate(undefined)}>
              {t("diagrams.sync")}
            </Button>
            <Button icon={<Workflow size={14} />} disabled={layout.isPending} onClick={() => layout.mutate(undefined)}>
              {t("diagrams.autolayout")}
            </Button>
            <Button
              icon={<Download size={14} />}
              onClick={() =>
                downloadSvg(
                  `${data.diagram.name}.svg`,
                  diagramToSvg(data.diagram.name, getNodes(), getEdges()),
                )
              }
            >
              {t("diagrams.exportSvg")}
            </Button>
            <Button variant="primary" icon={<Save size={14} />} disabled={!dirty || save.isPending} onClick={() => save.mutate(undefined)}>
              {t("diagrams.saveLayout")}
            </Button>
          </>
        }
      />
      {data.diagram.description && <p className="text-xs text-muted">{data.diagram.description}</p>}
      <FormError message={errorText} />
      {conflict && (
        <div className="flex items-center justify-between gap-3 rounded-md border border-app bg-[rgb(var(--warn)/0.12)] px-3 py-2 text-sm">
          <span>{t("diagrams.versionConflict")}</span>
          <Button
            onClick={() => {
              applied.current = null;
              setDirty(false);
              setConflict(false);
              void refetch();
            }}
          >
            {t("diagrams.reload")}
          </Button>
        </div>
      )}
      <div className="surface relative min-h-0 flex-1 overflow-hidden rounded-lg">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={diagramNodeTypes}
          edgeTypes={diagramEdgeTypes}
          colorMode={colorMode}
          nodesConnectable={false}
          deleteKeyCode={null}
          fitView={!data.diagram.viewport.zoom}
          defaultViewport={
            data.diagram.viewport.zoom
              ? {
                  x: data.diagram.viewport.x ?? 0,
                  y: data.diagram.viewport.y ?? 0,
                  zoom: data.diagram.viewport.zoom,
                }
              : undefined
          }
          onNodeDragStop={() => {
            setEdges((current) => retargetEdges(current, getNodes()));
            setDirty(true);
          }}
          onSelectionChange={({ nodes: picked }) => setSelectedId(picked[0]?.id ?? null)}
          onNodeDoubleClick={(_event, node) => {
            if (node.data.ciId) navigate(`/ci/${node.data.ciId}?tab=network`);
          }}
        >
          <Background />
          <Controls />
          <MiniMap pannable zoomable />
        </ReactFlow>
        <p className="pointer-events-none absolute bottom-2 left-2 text-[11px] text-muted">
          {t("diagrams.doubleClick")}
        </p>
      </div>
      <div className="flex justify-end">
        <Button variant="ghost" disabled={removeDiagram.isPending} onClick={() => removeDiagram.mutate(undefined)}>
          {t("diagrams.deleteTitle")}
        </Button>
      </div>
      {adding && (
        <AddNodeDialog
          diagramId={diagramId}
          diagramType={data.diagram.diagram_type}
          present={present}
          onClose={() => setAdding(false)}
          onBeforeAdd={async () => (dirty ? persist() : true)}
          onAdded={async () => {
            setDirty(false);
            applied.current = null;
            await refetch();
          }}
        />
      )}
    </div>
  );
}

export function DiagramEditorPage() {
  const { diagramId } = useParams();
  if (!diagramId) return null;
  return (
    <ReactFlowProvider>
      <Editor diagramId={diagramId} />
    </ReactFlowProvider>
  );
}
