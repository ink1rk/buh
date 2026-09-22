import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useSession } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";
import { Spinner } from "@/shared/ui/Layout";

export function LoginPage() {
  const { t, locale, setLocale } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const login = useApiMutation(mutations.login, [], {
    onSuccess: (user) => {
      queryClient.setQueryData(keys.session, user);
      setLocale(user.locale === "en" ? "en" : "ru");
      navigate("/dashboard", { replace: true });
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
  if (session.data) return <Navigate to="/dashboard" replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    login.mutate({ email: email.trim(), password });
  };

  return (
    <div className="flex h-full items-center justify-center bg-app px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <p className="text-2xl font-semibold tracking-tight">{t("app.name")}</p>
          <p className="mt-1 text-xs text-muted">{t("auth.subtitle")}</p>
        </div>

        <form onSubmit={submit} className="surface flex flex-col gap-3 rounded-lg p-5">
          <h1 className="text-sm font-semibold">{t("auth.title")}</h1>

          <Field label={t("auth.email")} required>
            <Input
              type="email"
              value={email}
              autoComplete="username"
              autoFocus
              required
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>

          <Field label={t("auth.password")} required error={error}>
            <Input
              type="password"
              value={password}
              autoComplete="current-password"
              required
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          <Button type="submit" variant="primary" disabled={login.isPending} className="mt-1">
            {login.isPending ? <Spinner className="h-3.5 w-3.5" /> : t("auth.submit")}
          </Button>
        </form>

        <div className="mt-3 text-center">
          <button
            type="button"
            onClick={() => setLocale(locale === "ru" ? "en" : "ru")}
            className="text-xs text-muted uppercase hover:text-app"
          >
            {locale === "ru" ? "English" : "Русский"}
          </button>
        </div>
      </div>
    </div>
  );
}
