import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useDocumentTemplates } from "@/shared/api/queries";
import { Button } from "@/shared/ui/Button";
import { PageHeader, Panel, Spinner } from "@/shared/ui/Layout";
import { toast } from "@/shared/ui/toast";

export function TemplatesPage() {
  const { t, te } = useI18n();
  const { data, isLoading } = useDocumentTemplates();
  const install = useApiMutation(() => mutations.installDocumentTemplates(), [keys.documentTemplates], {
    onSuccess: (result) =>
      toast.success(t("office.installedCount", { created: result.created, skipped: result.skipped })),
    onError: (err) => toast.error(describeError(err, t)),
  });
  const rows = data ?? [];

  return (
    <div className="flex flex-col gap-4" data-testid="office-templates">
      <PageHeader
        title={t("nav.templates")}
        subtitle={t("office.templatesHint")}
        actions={
          <Button variant="primary" disabled={install.isPending} onClick={() => install.mutate()}>
            {t("office.install")}
          </Button>
        }
      />
      {isLoading ? (
        <div className="flex h-40 items-center justify-center">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((item) => (
            <Panel key={item.title}>
              <p className="text-[11px] tracking-wide text-muted uppercase">
                {te("documentKind", item.kind)}
              </p>
              <h2 className="mt-1 text-sm font-medium">{item.title}</h2>
              <p className="mt-1 text-xs text-muted">{item.summary}</p>
              <div className="mt-3">
                {item.installed && item.document_id ? (
                  <Link to={`/documents/${item.document_id}`} className="text-sm text-[rgb(var(--accent))]">
                    {t("office.openDocument")}
                  </Link>
                ) : (
                  <span className="text-xs text-muted">{t("office.notInstalled")}</span>
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
