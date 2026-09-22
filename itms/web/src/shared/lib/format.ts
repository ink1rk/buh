const LOCALE_TAG: Record<string, string> = { ru: "ru-RU", en: "en-GB" };

function tag(locale: string): string {
  return LOCALE_TAG[locale] ?? "ru-RU";
}

export function formatDate(value: string | null | undefined, locale = "ru"): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(tag(locale), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined, locale = "ru"): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(tag(locale), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const RELATIVE_STEPS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 30],
  ["month", 12],
  ["year", Number.POSITIVE_INFINITY],
];

/** «3 минуты назад» — в ленте изменений это читается быстрее абсолютной даты. */
export function formatRelative(value: string | null | undefined, locale = "ru"): string {
  if (!value) return "—";
  const formatter = new Intl.RelativeTimeFormat(tag(locale), { numeric: "auto" });
  let delta = (new Date(value).getTime() - Date.now()) / 1000;
  for (const [unit, limit] of RELATIVE_STEPS) {
    if (Math.abs(delta) < limit) return formatter.format(Math.round(delta), unit);
    delta /= limit;
  }
  return formatDate(value, locale);
}

export function formatNumber(value: number | null | undefined, locale = "ru"): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(tag(locale));
}

export function formatPercent(value: number | null | undefined, locale = "ru"): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString(tag(locale), { maximumFractionDigits: 1 })} %`;
}

export function formatBytes(value: number, locale = "ru"): string {
  const units = ["Б", "КБ", "МБ", "ГБ"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toLocaleString(tag(locale), { maximumFractionDigits: 1 })} ${units[index]}`;
}

/** Значения аудита приходят как произвольный JSON и должны быть показаны без падения. */
export function formatAuditValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (Array.isArray(value)) return value.length ? value.map(formatAuditValue).join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
