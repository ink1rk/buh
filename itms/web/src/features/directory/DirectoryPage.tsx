import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import {
  keys,
  mutations,
  useApiMutation,
  useEmployees,
  useMeta,
  useResponsibilities,
  useWorkload,
} from "@/shared/api/queries";
import type { Employee } from "@/shared/api/types";
import { Badge, toneFor } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { DataTable, type Column } from "@/shared/ui/DataTable";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { BarList, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

function EmployeeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, te } = useI18n();
  const { data: meta } = useMeta();
  const { data: responsibilities } = useResponsibilities();

  const [fullName, setFullName] = useState("");
  const [position, setPosition] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [supportLine, setSupportLine] = useState("NONE");
  const [responsibilityId, setResponsibilityId] = useState("");

  const create = useApiMutation(
    (body: Record<string, unknown>) => mutations.createEmployee(body),
    [keys.employees, keys.workload, keys.dashboard],
    {
      onSuccess: () => {
        toast.success(t("app.created"));
        setFullName("");
        setPosition("");
        setEmail("");
        setPhone("");
        onClose();
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("directory.create")}
      width="sm"
      footer={
        <>
          <Button onClick={onClose}>{t("app.cancel")}</Button>
          <Button
            variant="primary"
            disabled={!fullName.trim() || create.isPending}
            onClick={() =>
              create.mutate({
                full_name: fullName.trim(),
                position: position.trim() || null,
                email: email.trim() || null,
                phone: phone.trim() || null,
                support_line: supportLine,
                responsibility_ids: responsibilityId ? [responsibilityId] : [],
              })
            }
          >
            {t("app.create")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label={t("directory.fullName")} required>
          <Input value={fullName} autoFocus onChange={(event) => setFullName(event.target.value)} />
        </Field>
        <Field label={t("directory.position")}>
          <Input value={position} onChange={(event) => setPosition(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("directory.email")}>
            <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <Field label={t("directory.phone")}>
            <Input value={phone} onChange={(event) => setPhone(event.target.value)} />
          </Field>
        </div>
        <Field label={t("directory.supportLine")}>
          <Select
            value={supportLine}
            onChange={(event) => setSupportLine(event.target.value)}
            options={(meta?.support_lines ?? []).map((value) => ({
              value,
              label: te("supportLine", value),
            }))}
          />
        </Field>
        <Field label={t("directory.responsibility")}>
          <Select
            value={responsibilityId}
            placeholder="—"
            onChange={(event) => setResponsibilityId(event.target.value)}
            options={(responsibilities ?? []).map((item) => ({
              value: item.id,
              label: item.name,
            }))}
          />
        </Field>
      </div>
    </Dialog>
  );
}

export function DirectoryPage() {
  const { t, te } = useI18n();
  const [createOpen, setCreateOpen] = useState(false);
  const { data: employees, isFetching } = useEmployees();
  const { data: workload } = useWorkload();

  const columns: Array<Column<Employee>> = [
    {
      key: "full_name",
      header: t("directory.fullName"),
      render: (row) => <span className="font-medium">{row.full_name}</span>,
    },
    {
      key: "position",
      header: t("directory.position"),
      render: (row) => <span className="text-muted">{row.position ?? "—"}</span>,
    },
    {
      key: "support_line",
      header: t("directory.supportLine"),
      width: "8rem",
      render: (row) => te("supportLine", row.support_line),
    },
    {
      key: "status",
      header: t("directory.status"),
      width: "9rem",
      render: (row) => (
        <Badge tone={toneFor("employeeStatus", row.status)}>
          {te("employeeStatus", row.status)}
        </Badge>
      ),
    },
    {
      key: "responsibilities",
      header: t("directory.responsibility"),
      render: (row) =>
        row.responsibilities.length ? (
          <span className="flex flex-wrap gap-1">
            {row.responsibilities.map((item) => (
              <Badge key={item.id}>{item.name}</Badge>
            ))}
          </span>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "contacts",
      header: t("directory.email"),
      width: "14rem",
      render: (row) => <span className="text-xs text-muted">{row.email ?? row.phone ?? "—"}</span>,
    },
  ];

  return (
    <>
      <PageHeader
        title={t("directory.title")}
        subtitle={t("directory.subtitle")}
        actions={
          <Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
            {t("directory.create")}
          </Button>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[1fr_20rem]">
        <Panel bodyClassName="p-0">
          <DataTable
            columns={columns}
            rows={employees ?? []}
            rowKey={(row) => row.id}
            loading={isFetching}
            emptyTitle={t("app.empty")}
            emptyHint={t("directory.emptyHint")}
          />
        </Panel>

        <Panel title={t("directory.workload")}>
          <BarList
            emptyLabel={t("app.empty")}
            items={(workload ?? []).map((row) => ({
              label: row.full_name,
              count: row.owned_ci,
            }))}
          />
          <p className="mt-3 border-t border-app pt-2 text-xs text-muted">
            {t("directory.workloadHint")}{" "}
            <Link to="/ci" className="text-accent hover:underline">
              {t("ci.title")}
            </Link>
          </p>
        </Panel>
      </div>

      <EmployeeDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}
