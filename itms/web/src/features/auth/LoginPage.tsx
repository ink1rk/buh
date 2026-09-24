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
    <div className="grid h-full lg:grid-cols-[1.15fr_0.85fr]">
      <aside className="relative hidden overflow-hidden bg-[#101412] text-[#f4f2ed] lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgb(14_110_102/0.45),transparent_42%),radial-gradient(circle_at_80%_90%,rgb(14_110_102/0.2),transparent_36%)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.18]"
          style={{
            backgroundImage:
              "linear-gradient(rgb(255 255 253 / 0.16) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 253 / 0.16) 1px, transparent 1px)",
            backgroundSize: "72px 72px",
            maskImage: "radial-gradient(ellipse at center, black, transparent 75%)",
          }}
        />
        <div className="relative flex items-center gap-3">
          <Mark size={36} />
          <p className="text-lg font-semibold tracking-tight">{t("app.name")}</p>
        </div>
        <div className="relative max-w-md">
          <p className="text-4xl leading-[1.05] font-semibold tracking-[-0.04em]">{t("app.tagline")}</p>
          <p className="mt-4 text-base text-[#c8c4bb]">{t("auth.subtitle")}</p>
        </div>
      </aside>

      <div className="flex items-center justify-center bg-app px-6 py-10">
        <div className="w-full max-w-[22rem]">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <Mark size={32} />
            <div>
              <p className="text-lg font-semibold tracking-tight">{t("app.name")}</p>
              <p className="text-xs text-muted">{t("app.tagline")}</p>
            </div>
          </div>

          <form onSubmit={submit} className="flex flex-col gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{t("auth.title")}</h1>
              <p className="mt-1 text-sm text-muted">{t("auth.subtitle")}</p>
            </div>

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

            <Button type="submit" variant="primary" disabled={login.isPending} className="mt-1 h-10">
              {login.isPending ? <Spinner className="h-3.5 w-3.5" /> : t("auth.submit")}
            </Button>
          </form>

          <div className="mt-6">
            <button
              type="button"
              onClick={() => setLocale(locale === "ru" ? "en" : "ru")}
              className="text-xs font-medium tracking-wide text-muted uppercase hover:text-app"
            >
              {locale === "ru" ? "English" : "Русский"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
