import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useSession } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";
import { Spinner } from "@/shared/ui/Layout";
import { Mark } from "@/shared/ui/Mark";

export function FirstPasswordPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSession();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const changePassword = useApiMutation(mutations.changePassword, [], {
    onSuccess: () => {
      queryClient.setQueryData(keys.session, null);
      navigate("/login", { replace: true, state: { passwordChanged: true } });
    },
    onError: (err) => setError(describeError(err, t)),
  });

  if (session.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-app">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!session.data) return <Navigate to="/login" replace />;
  if (!session.data.must_change_password) return <Navigate to="/dashboard" replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    setError(null);
    changePassword.mutate({ current_password: currentPassword, new_password: newPassword });
  };

  return (
    <div className="flex h-full items-center justify-center bg-app px-6 py-10">
      <form onSubmit={submit} className="w-full max-w-[24rem] flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <Mark size={32} />
          <p className="text-lg font-semibold tracking-tight">{t("app.name")}</p>
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("auth.firstTitle")}</h1>
          <p className="mt-2 text-sm text-muted">{t("auth.firstText")}</p>
          <p className="mt-2 text-sm text-app">{session.data.email}</p>
        </div>

        <Field label={t("settings.currentPassword")} required>
          <Input
            type="password"
            value={currentPassword}
            autoComplete="current-password"
            autoFocus
            required
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </Field>
        <Field label={t("settings.newPassword")} required hint={t("settings.passwordHint")}>
          <Input
            type="password"
            value={newPassword}
            autoComplete="new-password"
            required
            minLength={10}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </Field>
        <Field label={t("auth.confirmPassword")} required error={error}>
          <Input
            type="password"
            value={confirmPassword}
            autoComplete="new-password"
            required
            minLength={10}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </Field>

        <Button
          type="submit"
          variant="primary"
          disabled={changePassword.isPending || newPassword.length < 10}
          className="mt-1 h-10"
        >
          {changePassword.isPending ? <Spinner className="h-3.5 w-3.5" /> : t("app.save")}
        </Button>
      </form>
    </div>
  );
}
