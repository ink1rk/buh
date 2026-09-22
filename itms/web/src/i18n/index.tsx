import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { useUiStore } from "@/shared/store/ui";

import { en } from "./en";
import { ru, type Dictionary } from "./ru";

export type Locale = "ru" | "en";

const DICTIONARIES: Record<Locale, unknown> = { ru, en };

/** Ключи словаря в виде "ci.status" — путь проверяется компилятором. */
type Path<T> = {
  [K in keyof T & string]: T[K] extends Record<string, unknown> ? `${K}.${Path<T[K]>}` : K;
}[keyof T & string];

export type TranslationKey = Path<Dictionary>;

function lookup(dictionary: unknown, key: string): string | undefined {
  const value = key
    .split(".")
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === "object" ? (acc as Record<string, unknown>)[part] : undefined,
      dictionary,
    );
  return typeof value === "string" ? value : undefined;
}

export type Translate = (key: TranslationKey, vars?: Record<string, string | number>) => string;

interface I18nValue {
  locale: Locale;
  t: Translate;
  /** Перевод значения перечисления: неизвестные значения показываются как есть. */
  te: (group: keyof Dictionary["enums"], value: string | null | undefined) => string;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const locale = useUiStore((state) => state.locale);
  const setLocale = useUiStore((state) => state.setLocale);

  const t = useCallback<Translate>(
    (key, vars) => {
      // Запасной вариант — русский: неполный перевод не должен ломать интерфейс.
      const raw = lookup(DICTIONARIES[locale], key) ?? lookup(ru, key) ?? key;
      if (!vars) return raw;
      return raw.replace(/\{(\w+)\}/g, (match, name: string) =>
        name in vars ? String(vars[name]) : match,
      );
    },
    [locale],
  );

  const te = useCallback<I18nValue["te"]>(
    (group, value) => {
      if (!value) return "—";
      const key = `enums.${group}.${value}` as TranslationKey;
      const translated = lookup(DICTIONARIES[locale], key) ?? lookup(ru, key);
      return translated ?? value;
    },
    [locale],
  );

  const value = useMemo<I18nValue>(() => ({ locale, t, te, setLocale }), [locale, t, te, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n используется вне I18nProvider");
  return context;
}

const PLURAL_RULES = new Intl.PluralRules("ru-RU");

/** «1 задача», «2 задачи», «5 задач» — без этого интерфейс выглядит неряшливо. */
export function plural(count: number, forms: [string, string, string]): string {
  const category = PLURAL_RULES.select(count);
  const index = category === "one" ? 0 : category === "few" ? 1 : 2;
  return `${count} ${forms[index]}`;
}
