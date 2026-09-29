import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ReasonField } from "@/features/provenance/ReasonField";
import { useI18n } from "@/i18n";
import { api, type Provenance } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import { mutations, useApiMutation, useSession } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Dialog } from "@/shared/ui/Dialog";
import { Field, Input, Select } from "@/shared/ui/Field";
import { FormError, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

interface Account {
  id: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  last_login_at: string | null;
}

const ROLES = ["VIEWER", "OPERATOR", "ENGINEER", "OWNER"] as const;

export function UsersPanel() {
  const { t, te } = useI18n();
  const { data: session } = useSession();
  const canManage = session?.permissions.includes("user:manage") ?? false;
  const canGrantOwner = session?.permissions.includes("user:grant_owner") ?? false;
  const roles = canGrantOwner ? ROLES : ROLES.filter((role) => role !== "OWNER");

  const { data: users } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<Account[]>("/users"),
    enabled: canManage,
  });

  const [creating, setCreating] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<string>("VIEWER");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Account | null>(null);
  const [nextRole, setNextRole] = useState("VIEWER");
  const [reason, setReason] = useState<Provenance>({});

  const create = useApiMutation((body: Record<string, unknown>) => mutations.createUser(body), [
    ["users"],
  ], {
    onSuccess: () => {
      toast.success(t("app.created"));
      setCreating(false);
      setEmail("");
      setName("");
      setPassword("");
      setRole("VIEWER");
      setError(null);
    },
    onError: (err) => setError(describeError(err, t)),
  });

  const update = useApiMutation(
    (input: { id: string; body: Record<string, unknown>; provenance: Provenance }) =>
      mutations.updateUser(input.id, input.body, input.provenance),
    [["users"]],
    {
      onSuccess: () => {
        toast.success(t("app.saved"));
        setPending(null);
        setReason({});
      },
      onError: (err) => setError(describeError(err, t)),
    },
  );

  if (!canManage) return null;

  return (
    <Panel title={t("settings.users")} className="mt-4">
      <p className="mb-3 text-xs text-muted">{t("settings.usersHint")}</p>
      <div className="mb-3">
        <Button data-testid="users-add" onClick={() => setCreating(true)}>
          {t("settings.addUser")}
        </Button>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>
            <th className="py-1 pr-3 font-medium">{t("settings.displayName")}</th>
            <th className="py-1 pr-3 font-medium">{t("auth.email")}</th>
            <th className="py-1 pr-3 font-medium">{t("settings.changeRole")}</th>
            <th className="py-1 pr-3 font-medium">{t("directory.status")}</th>
            <th className="py-1 pr-3 font-medium">{t("settings.lastLogin")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(users ?? []).map((user) => (
            <tr key={user.id} className="border-t border-app" data-testid="user-row">
              <td className="py-1.5 pr-3">{user.display_name}</td>
              <td className="py-1.5 pr-3 text-muted">{user.email}</td>
              <td className="py-1.5 pr-3">{te("userRole", user.role)}</td>
              <td className="py-1.5 pr-3">{te("userStatus", user.status)}</td>
              <td className="py-1.5 pr-3 text-muted">
                {user.last_login_at ? new Date(user.last_login_at).toLocaleString("ru-RU") : "—"}
              </td>
              <td className="py-1.5 text-right">
                {user.id !== session?.id && (
                  <span className="inline-flex gap-2">
                    <Button
                      onClick={() => {
                        setPending(user);
                        setNextRole(user.role);
                        setReason({});
                        setError(null);
                      }}
                    >
                      {t("settings.changeRole")}
                    </Button>
                    <Button
                      data-testid="users-deactivate"
                      onClick={() => {
                        setError(null);
                        update.mutate({
                          id: user.id,
                          body: { status: user.status === "ACTIVE" ? "DISABLED" : "ACTIVE" },
                          provenance: { reason: t("settings.deactivate") },
                        });
                      }}
                    >
                      {user.status === "ACTIVE" ? t("settings.deactivate") : t("settings.activate")}
                    </Button>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title={t("settings.addUser")}
        footer={
          <>
            <Button onClick={() => setCreating(false)}>{t("app.cancel")}</Button>
            <Button
              variant="primary"
              data-testid="users-save"
              disabled={!email.trim() || !name.trim() || !password || create.isPending}
              onClick={() =>
                create.mutate({
                  email: email.trim(),
                  display_name: name.trim(),
                  password,
                  role,
                })
              }
            >
              {t("app.create")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label={t("settings.displayName")} required>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label={t("auth.email")} required>
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label={t("auth.password")} required hint={t("settings.passwordHint")}>
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Field label={t("settings.changeRole")}>
            <Select
              value={role}
              options={roles.map((item) => ({ value: item, label: te("userRole", item) }))}
              onChange={(event) => setRole(event.target.value)}
            />
          </Field>
          <FormError message={error} />
        </div>
      </Dialog>

      <Dialog
        open={pending !== null}
        onClose={() => setPending(null)}
        title={t("settings.changeRole")}
        footer={
          <>
            <Button onClick={() => setPending(null)}>{t("app.cancel")}</Button>
            <Button
              variant="primary"
              disabled={!reason.reason?.trim() || update.isPending || !pending}
              onClick={() => {
                if (!pending) return;
                update.mutate({
                  id: pending.id,
                  body: { role: nextRole },
                  provenance: reason,
                });
              }}
            >
              {t("app.save")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label={t("settings.changeRole")}>
            <Select
              value={nextRole}
              options={roles.map((item) => ({ value: item, label: te("userRole", item) }))}
              onChange={(event) => setNextRole(event.target.value)}
            />
          </Field>
          <ReasonField value={reason} onChange={setReason} required />
          <FormError message={error} />
        </div>
      </Dialog>
    </Panel>
  );
}
