import { Link } from "react-router-dom";

import { useI18n } from "@/i18n";
import { PageHeader } from "@/shared/ui/Layout";

const LINKS = [
  {
    to: "/racks",
    title: "Стойки",
    hint: "Фасад, юниты, вес и мощность. Оборудование ставится на конкретное место, а не списком.",
  },
  {
    to: "/floorplans",
    title: "Планы помещений",
    hint: "Стойки и щиты на плане в миллиметрах.",
  },
  {
    to: "/locations",
    title: "Размещения",
    hint: "Площадка, зал, ряд и комната — дерево, к которому привязаны объекты.",
  },
];

export function DatacenterPage() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader
        title={t("nav.datacenter")}
        subtitle="Где физически находится инфраструктура: зал, стойка и план."
      />
      <div className="grid gap-3 md:grid-cols-3">
        {LINKS.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="surface rounded-lg px-4 py-3.5 transition-colors hover:bg-[rgb(var(--surface-muted))]"
          >
            <p className="text-sm font-semibold">{item.title}</p>
            <p className="mt-1 text-[13px] leading-5 text-muted">{item.hint}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
