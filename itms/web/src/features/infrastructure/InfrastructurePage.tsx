import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { useDashboard } from "@/shared/api/queries";
import { PageHeader, Panel, Spinner } from "@/shared/ui/Layout";

const LINKS: Array<{ to: string; title: string; hint: string }> = [
  { to: "/ci", title: "Объекты", hint: "Единый реестр: серверы, сервисы, узлы питания и всё, что состоит в модели." },
  { to: "/devices", title: "Оборудование", hint: "Роли, интерфейсы и то, что стоит в стойках." },
  { to: "/ipam", title: "Адресация", hint: "Сети, VLAN и адреса." },
  { to: "/network", title: "Сеть", hint: "Соединения и трассировка." },
  { to: "/diagrams", title: "Схемы", hint: "Топология и однолинейная схема питания." },
  { to: "/datacenter", title: "Дата-центр", hint: "Стойки, планы помещений и размещения." },
  { to: "/power", title: "Питание", hint: "Цепочка, запас и прогноз нагрузки." },
];

export function InfrastructurePage() {
  const { t, te } = useI18n();
  const { data, isPending } = useDashboard();
  return (
    <>
      <PageHeader title={t("nav.infrastructure")} subtitle={t("dashboard.healthTitle")} />
      {isPending || !data ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : (
        <Panel title={t("dashboard.byType")}>
          <ul className="flex flex-wrap gap-2">
            {data.ci_by_type.map((row) => (
              <li key={row.key}>
                <Link
                  to={`/ci?type=${row.key}`}
                  className="inline-flex items-center gap-2 rounded-md border border-app px-2.5 py-1.5 text-sm hover:bg-[rgb(var(--surface-muted))]"
                >
                  <span>{te("ciType", row.key)}</span>
                  <span className="tabular-nums text-muted">{row.count}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {LINKS.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="card px-4 py-3 transition-colors hover:bg-[rgb(var(--surface-muted))]"
          >
            <p className="text-sm font-semibold">{item.title}</p>
            <p className="mt-1 text-[13px] leading-5 text-muted">{item.hint}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
