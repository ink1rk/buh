import { keys, mutations, useApiMutation, useTransition } from "@/shared/api/queries";
import type { TransitionView } from "@/shared/api/types";
import { describeError } from "@/shared/api/errors";
import { useI18n } from "@/i18n";
import { formatDateTime } from "@/shared/lib/format";
import { Badge, type Tone } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function formatKw(watts: number | null): string {
  if (watts == null) return "—";
  return `${(watts / 1000).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} кВт`;
}

function gapTone(level: string): Tone {
  if (level === "BLOCKER") return "danger";
  if (level === "WARNING") return "warn";
  if (level === "OK") return "ok";
  return "neutral";
}

function headroomTone(watts: number | null): Tone {
  if (watts == null) return "neutral";
  if (watts < 0) return "danger";
  if (watts < 1000) return "warn";
  return "ok";
}

function Metric({
  label,
  watts,
  testId,
  tone,
}: {
  label: string;
  watts: number | null;
  testId?: string;
  tone?: Tone;
}) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div
        className="text-lg font-semibold tabular-nums"
        data-testid={testId}
        data-watts={watts ?? ""}
      >
        {tone ? <Badge tone={tone}>{formatKw(watts)}</Badge> : formatKw(watts)}
      </div>
    </div>
  );
}

export function TransitionPanel({ projectId }: { projectId: string }) {
  const { t, te, locale } = useI18n();
  const { data, isLoading } = useTransition(projectId);
  const invalidate = [
    keys.projects,
    keys.project(projectId),
    keys.power,
    keys.transition(projectId),
  ];
  const saved = {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err: unknown) => toast.error(describeError(err, t)),
  };
  const snap = useApiMutation(
    (name: string) => mutations.takeSnapshot(projectId, name),
    invalidate,
    saved,
  );
  const plan = useApiMutation(() => mutations.buildPlan(projectId), invalidate, saved);
  const apply = useApiMutation(
    (planId: string) => mutations.applyPlan(projectId, planId, { projectId }),
    invalidate,
    saved,
  );
  const rollback = useApiMutation(
    (planId: string) => mutations.rollbackPlan(projectId, planId, { projectId }),
    invalidate,
    saved,
  );

  if (isLoading || !data) {
    return <p className="text-sm text-muted">{t("app.loading")}</p>;
  }

  const live = data.live;
  const active = data.plans.find((item) => item.status !== "CANCELLED");
  const busy = snap.isPending || plan.isPending || apply.isPending || rollback.isPending;

  return (
    <div className="flex flex-col gap-4" data-testid="transition-panel">
      <Panel title={t("projects.liveNow")}>
        {live.target_w == null ? (
          <p className="text-sm text-muted">{t("projects.noForecast")}</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <Metric label={t("projects.estimated")} watts={live.estimated_w} />
            <Metric label={t("projects.nameplate")} watts={live.nameplate_w} />
            <Metric label={t("projects.limit")} watts={live.limit_w} />
            <Metric
              label={t("projects.headroom")}
              watts={live.headroom_w}
              testId="live-headroom"
              tone={headroomTone(live.headroom_w)}
            />
            <Metric label={t("projects.target")} watts={live.target_w} />
            <Metric
              label={t("projects.deficit")}
              watts={live.deficit_w}
              testId="live-deficit"
              tone={live.deficit_w && live.deficit_w > 0 ? "danger" : "ok"}
            />
            <Metric label={t("projects.required")} watts={live.required_w} />
            <Metric label={t("projects.recommended")} watts={live.recommended_w} />
          </div>
        )}
      </Panel>

      <Panel
        title={t("projects.gap")}
        actions={
          <div className="flex gap-1.5">
            <Button
              size="sm"
              data-testid="take-snapshot"
              disabled={busy}
              onClick={() => snap.mutate(t("projects.snapshotName"))}
            >
              {t("projects.takeSnapshot")}
            </Button>
            {!active && (
              <Button
                size="sm"
                variant="primary"
                data-testid="build-plan"
                disabled={busy || live.target_w == null}
                onClick={() => plan.mutate()}
              >
                {t("projects.buildPlan")}
              </Button>
            )}
          </div>
        }
      >
        {data.gap.length === 0 ? (
          <p className="text-sm text-muted">{t("projects.noForecast")}</p>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="transition-gap">
            {data.gap.map((item) => (
              <li key={item.rule} className="flex items-start gap-2 text-sm">
                <Badge tone={gapTone(item.level)}>{te("gapLevel", item.level)}</Badge>
                <span>{item.message}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {data.plans.map((item) => (
        <PlanCard
          key={item.id}
          plan={item}
          busy={busy}
          onApply={() => apply.mutate(item.id)}
          onRollback={() => rollback.mutate(item.id)}
        />
      ))}

      {data.snapshots.length > 0 && (
        <Panel title={t("projects.snapshots")}>
          <ul className="flex flex-col gap-1 text-sm">
            {data.snapshots.map((item) => (
              <li key={item.id} className="flex items-baseline justify-between gap-3">
                <span>{item.name}</span>
                <span className="text-xs text-muted">
                  {formatDateTime(item.taken_at, locale)} · {formatKw(item.limit_w)} ·{" "}
                  {t("projects.deficit")} {formatKw(item.deficit_w)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function PlanCard({
  plan,
  busy,
  onApply,
  onRollback,
}: {
  plan: TransitionView["plans"][number];
  busy: boolean;
  onApply: () => void;
  onRollback: () => void;
}) {
  const { t, te } = useI18n();
  const applied = plan.status === "APPLIED";
  return (
    <Panel
      title={plan.name}
      actions={
        <div className="flex items-center gap-1.5">
          <Badge tone={applied ? "ok" : "warn"}>{te("planStatus", plan.status)}</Badge>
          {applied ? (
            <Button size="sm" data-testid="rollback-plan" disabled={busy} onClick={onRollback}>
              {t("projects.rollbackPlan")}
            </Button>
          ) : (
            plan.status !== "CANCELLED" && (
              <Button
                size="sm"
                variant="primary"
                data-testid="apply-plan"
                disabled={busy}
                onClick={onApply}
              >
                {t("projects.applyPlan")}
              </Button>
            )
          )}
        </div>
      }
    >
      <ul className="flex flex-col gap-2 text-sm">
        {plan.items.map((item) => {
          const before = item.payload.before?.max_load_w;
          const next = item.payload.fields?.max_load_w;
          const showsWatts = before != null || next != null;
          return (
            <li key={item.id} data-testid="plan-item" data-ref={item.payload.ref ?? ""}>
              <div className="flex items-start gap-2">
                <Badge tone="neutral">{te("changeOperation", item.operation)}</Badge>
                <span>{item.payload.summary}</span>
              </div>
              {showsWatts && (
                <div className="mt-1 text-xs text-muted">
                  {t("projects.was")} {formatKw(before ?? null)} · {t("projects.becomes")}{" "}
                  {formatKw(next ?? null)}
                  {item.payload.fields?.rated_current_a != null &&
                    ` · ${item.payload.fields.rated_current_a} А`}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
