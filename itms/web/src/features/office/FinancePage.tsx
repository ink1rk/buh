import { Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useDepartments,
  useFinance,
} from "@/shared/api/queries";
import type { FinanceEntry } from "@/shared/api/types";
import { Button, IconButton } from "@/shared/ui/Button";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, Metric, PageHeader, Panel } from "@/shared/ui/Layout";
import { Tabs } from "@/shared/ui/Tabs";
import { toast } from "@/shared/ui/toast";

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

function amount(value: string | number): number {
  return Number(value) || 0;
}

function monthKey(period: string): string {
  return period.slice(0, 7);
}

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function FinancePage() {
  const { t } = useI18n();
  const [kind, setKind] = useState("BUDGET");
  const [filterId, setFilterId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [direction, setDirection] = useState("OUT");
  const [period, setPeriod] = useState(currentMonth);
  const [article, setArticle] = useState("");
  const [planned, setPlanned] = useState("");
  const [actual, setActual] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: departments } = useDepartments();
  const { data, isLoading } = useFinance(kind);

  const rows = useMemo(() => {
    const items = data ?? [];
    if (!filterId) return items;
    return items.filter((item) => item.department_id === filterId);
  }, [data, filterId]);

  const save = useApiMutation(
    (body: Record<string, unknown>) => mutations.createFinance(body),
    [keys.finance(kind)],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setArticle("");
        setPlanned("");
        setActual("");
        setNotes("");
        setError(null);
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );
  const patch = useApiMutation(
    (body: { id: string; planned: string; actual: string }) =>
      mutations.updateFinance(body.id, { planned: body.planned, actual: body.actual }),
    [keys.finance(kind)],
    { onError: (err) => toast.error(describeError(err, t)) },
  );
  const remove = useApiMutation((id: string) => mutations.deleteFinance(id), [keys.finance(kind)], {
    onSuccess: () => toast.success(t("app.saved")),
    onError: (err) => toast.error(describeError(err, t)),
  });

  const incomePlan = rows
    .filter((row) => row.direction === "IN")
    .reduce((sum, row) => sum + amount(row.planned), 0);
  const incomeFact = rows
    .filter((row) => row.direction === "IN")
    .reduce((sum, row) => sum + amount(row.actual), 0);
  const expensePlan = rows
    .filter((row) => row.direction === "OUT")
    .reduce((sum, row) => sum + amount(row.planned), 0);
  const expenseFact = rows
    .filter((row) => row.direction === "OUT")
    .reduce((sum, row) => sum + amount(row.actual), 0);

  const months = [...new Set(rows.map((row) => monthKey(row.period)))].sort();

  return (
    <div className="flex flex-col gap-4" data-testid="office-finance">
      <PageHeader
        title={t("nav.budget")}
        subtitle={kind === "BUDGET" ? t("office.budgetHint") : t("office.cashflowHint")}
      />
      <Tabs
        items={[
          { id: "BUDGET", label: t("office.budget") },
          { id: "CASHFLOW", label: t("office.cashflow") },
        ]}
        active={kind}
        onChange={setKind}
      />
      <Field label={t("office.department")} className="max-w-xs">
        <Select
          value={filterId}
          placeholder={t("app.all")}
          onChange={(event) => setFilterId(event.target.value)}
          options={(departments ?? []).map((item) => ({ value: item.id, label: item.name }))}
        />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label={t("office.income")} value={money.format(incomeFact)} />
        <Metric label={t("office.expense")} value={money.format(expenseFact)} />
        <Metric label={t("office.balance")} value={money.format(incomeFact - expenseFact)} />
      </div>
      <Panel title={t("office.addLine")}>
        <div className="grid items-end gap-2 md:grid-cols-3 xl:grid-cols-6">
          <Field label={t("office.department")}>
            <Select
              value={departmentId}
              placeholder="—"
              onChange={(event) => setDepartmentId(event.target.value)}
              options={(departments ?? []).map((item) => ({ value: item.id, label: item.name }))}
            />
          </Field>
          <Field label={t("office.direction")}>
            <Select
              value={direction}
              onChange={(event) => setDirection(event.target.value)}
              options={[
                { value: "IN", label: t("office.income") },
                { value: "OUT", label: t("office.expense") },
              ]}
            />
          </Field>
          <Field label={t("office.period")}>
            <Input type="month" value={period} onChange={(event) => setPeriod(event.target.value)} />
          </Field>
          <Field label={t("office.article")}>
            <Input value={article} onChange={(event) => setArticle(event.target.value)} />
          </Field>
          <Field label={t("office.planned")}>
            <Input value={planned} onChange={(event) => setPlanned(event.target.value)} />
          </Field>
          <Field label={t("office.actual")}>
            <Input value={actual} onChange={(event) => setActual(event.target.value)} />
          </Field>
        </div>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <Field label={t("office.notes")} className="min-w-64 flex-1">
            <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Field>
          <Button
            variant="primary"
            disabled={!article.trim() || !period || save.isPending}
            onClick={() =>
              save.mutate({
                department_id: departmentId || null,
                kind,
                direction,
                period: `${period}-01`,
                article: article.trim(),
                planned: amount(planned),
                actual: amount(actual),
                notes: notes.trim() || null,
              })
            }
          >
            {t("app.save")}
          </Button>
        </div>
        <FormError message={error} />
      </Panel>
      {isLoading ? (
        <p className="text-sm text-muted">{t("app.loading")}</p>
      ) : months.length === 0 ? (
        <p className="text-sm text-muted">{t("app.empty")}</p>
      ) : (
        months.map((month) => (
          <MonthTable
            key={month}
            month={month}
            rows={rows.filter((row) => monthKey(row.period) === month)}
            onPatch={(row, plannedValue, actualValue) =>
              patch.mutate({ id: row.id, planned: plannedValue, actual: actualValue })
            }
            onDelete={(id) => remove.mutate(id)}
            departmentName={(id) =>
              (departments ?? []).find((item) => item.id === id)?.name ?? ""
            }
          />
        ))
      )}
      <p className="text-xs text-muted">
        {t("office.planFact", {
          plan: money.format(incomePlan - expensePlan),
          fact: money.format(incomeFact - expenseFact),
        })}
      </p>
    </div>
  );
}

function MonthTable({
  month,
  rows,
  onPatch,
  onDelete,
  departmentName,
}: {
  month: string;
  rows: FinanceEntry[];
  onPatch: (row: FinanceEntry, planned: string, actual: string) => void;
  onDelete: (id: string) => void;
  departmentName: (id: string) => string;
}) {
  const { t } = useI18n();
  return (
    <Panel title={month}>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="py-1 pr-2 font-medium">{t("office.article")}</th>
              <th className="py-1 pr-2 font-medium">{t("office.direction")}</th>
              <th className="py-1 pr-2 font-medium">{t("office.planned")}</th>
              <th className="py-1 pr-2 font-medium">{t("office.actual")}</th>
              <th className="py-1 pr-2 font-medium">{t("office.variance")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <FinanceRow
                key={row.id}
                row={row}
                department={row.department_id ? departmentName(row.department_id) : ""}
                onPatch={onPatch}
                onDelete={onDelete}
              />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function FinanceRow({
  row,
  department,
  onPatch,
  onDelete,
}: {
  row: FinanceEntry;
  department: string;
  onPatch: (row: FinanceEntry, planned: string, actual: string) => void;
  onDelete: (id: string) => void;
}) {
  const { t } = useI18n();
  const [planned, setPlanned] = useState(String(amount(row.planned)));
  const [actual, setActual] = useState(String(amount(row.actual)));
  const variance = amount(actual) - amount(planned);
  return (
    <tr className="border-t border-app">
      <td className="py-2 pr-2">
        <span className="block">{row.article}</span>
        {(department || row.notes) && (
          <span className="text-xs text-muted">
            {[department, row.notes].filter(Boolean).join(" · ")}
          </span>
        )}
      </td>
      <td className="py-2 pr-2 text-muted">
        {row.direction === "IN" ? t("office.income") : t("office.expense")}
      </td>
      <td className="py-2 pr-2">
        <Input
          className="w-28"
          value={planned}
          onChange={(event) => setPlanned(event.target.value)}
          onBlur={() => {
            if (planned !== String(amount(row.planned))) onPatch(row, planned, actual);
          }}
        />
      </td>
      <td className="py-2 pr-2">
        <Input
          className="w-28"
          value={actual}
          onChange={(event) => setActual(event.target.value)}
          onBlur={() => {
            if (actual !== String(amount(row.actual))) onPatch(row, planned, actual);
          }}
        />
      </td>
      <td className="py-2 pr-2 tabular-nums">{money.format(variance)}</td>
      <td className="py-2 text-right">
        <IconButton label={t("app.delete")} onClick={() => onDelete(row.id)}>
          <Trash2 size={13} />
        </IconButton>
      </td>
    </tr>
  );
}
