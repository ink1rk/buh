import type { Translate, TranslationKey } from "@/i18n";

import { ApiError } from "./client";

/**
 * Сообщение с сервера уже на русском, но код ошибки даёт более точную формулировку
 * и позволяет перевести её на выбранный язык интерфейса. Если перевода нет,
 * показывается серверный текст.
 */
export function describeError(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    const key = `errors.${error.code}` as TranslationKey;
    const translated = t(key);
    if (translated !== key) return translated;
    return error.message || t("app.error");
  }
  if (error instanceof Error) return error.message;
  return t("app.error");
}
