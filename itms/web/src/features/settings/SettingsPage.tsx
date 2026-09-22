import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useI18n } from "@/i18n";
import { api } from "@/shared/api/client";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useMeta, useSession } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";
import { KeyValue, PageHeader, Panel } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

interface Organization {
  id: string;
  name: string;
  full_name: string | null;
  inn: string | null;
  address: string | null;
  timezone: string;
  notes: string | null;
}

export function SettingsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const { data: meta } = useMeta();

  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [orgName, setOrgName] = useState("");
  const [orgAddress, setOrgAddress] = useState("");

  useEffect(() => {
    if (session) setDisplayName(session.display_name);
  }, [session]);

  useEffect(() => {
    // Организация может быть ещё не заведена — это нормальное состояние.
    api
      .get<Organization | null>("/directory/organization")
      .then((data) => {
        setOrganization(data);
        setOrgName(data?.name ?? "");
        setOrgAddress(data?.address ?? "");
      })
      .catch(() => setOrganization(null));
  }, []);

  const saveProfile = useApiMutation(
    (body: Record<string, unknown>) => mutations.updateProfile(body),
    [keys.session],
    {
      onSuccess: () => toast.success(t("app.saved")),
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const changePassword = useApiMutation(
    (body: { current_password: string; new_password: string }) => mutations.changePassword(body),
    [],
    {
      onSuccess: () => {
        toast.success(t("settings.passwordChanged"));
        setCurrentPassword("");
        setNewPassword("");
        queryClient.clear();
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const saveOrganization = useApiMutation(
    (body: Record<string, unknown>) => api.put<Organization>("/directory/organization", body),
    [],
    {
      onSuccess: (data) => {
        setOrganization(data);
        toast.success(t("app.saved"));
      },
      onError: (error) => toast.error(describeError(error, t)),
    },
  );

  const power = meta?.power_defaults;

  return (
    <>
      <PageHeader title={t("settings.title")} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={t("settings.profile")}>
          <div className="flex flex-col gap-3">
            <Field label={t("settings.displayName")}>
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </Field>
            <KeyValue
              items={[
                { label: t("auth.email"), value: session?.email ?? "—" },
                { label: t("directory.status"), value: session?.role ?? "—" },
              ]}
            />
            <Button
              variant="primary"
              className="self-start"
              disabled={saveProfile.isPending || !displayName.trim()}
              onClick={() => saveProfile.mutate({ display_name: displayName.trim() })}
            >
              {t("app.save")}
            </Button>
          </div>
        </Panel>

        <Panel title={t("settings.changePassword")}>
          <div className="flex flex-col gap-3">
            <Field label={t("settings.currentPassword")}>
              <Input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </Field>
            <Field label={t("settings.newPassword")} hint={t("settings.passwordHint")}>
              <Input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </Field>
            <Button
              variant="primary"
              className="self-start"
              disabled={
                changePassword.isPending || !currentPassword || newPassword.length < 10
              }
              onClick={() =>
                changePassword.mutate({
                  current_password: currentPassword,
                  new_password: newPassword,
                })
              }
            >
              {t("app.save")}
            </Button>
          </div>
        </Panel>

        <Panel title={t("settings.organization")}>
          <div className="flex flex-col gap-3">
            <Field label={t("ci.name")} required>
              <Input value={orgName} onChange={(event) => setOrgName(event.target.value)} />
            </Field>
            <Field label={t("locations.address")}>
              <Input value={orgAddress} onChange={(event) => setOrgAddress(event.target.value)} />
            </Field>
            <Button
              variant="primary"
              className="self-start"
              disabled={!orgName.trim() || saveOrganization.isPending}
              onClick={() =>
                saveOrganization.mutate({
                  name: orgName.trim(),
                  address: orgAddress.trim() || null,
                  full_name: organization?.full_name ?? null,
                  inn: organization?.inn ?? null,
                  timezone: organization?.timezone ?? null,
                  notes: organization?.notes ?? null,
                })
              }
            >
              {t("app.save")}
            </Button>
          </div>
        </Panel>

        <Panel title={t("settings.powerDefaults")}>
          <p className="mb-3 text-xs text-muted">{t("settings.powerDefaultsHint")}</p>
          <KeyValue
            items={[
              { label: t("settings.voltageSingle"), value: `${power?.voltage_single_v ?? "—"} В` },
              { label: t("settings.voltageThree"), value: `${power?.voltage_three_v ?? "—"} В` },
              { label: t("settings.powerFactor"), value: power?.power_factor ?? "—" },
              { label: t("settings.derating"), value: power?.derating ?? "—" },
              { label: t("settings.reserve"), value: `${power?.reserve_target_pct ?? "—"} %` },
              {
                label: t("settings.measurementTtl"),
                value: power?.measurement_ttl_days ?? "—",
              },
              {
                label: t("settings.disbalance"),
                value: `${power?.phase_disbalance_limit_pct ?? "—"} %`,
              },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}
