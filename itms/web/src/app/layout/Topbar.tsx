import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useI18n } from "@/i18n";
import { describeError } from "@/shared/api/errors";
import { keys, mutations, useApiMutation, useSession } from "@/shared/api/queries";
import { useUiStore, type Theme } from "@/shared/store/ui";
import { IconButton } from "@/shared/ui/Button";
import { toast } from "@/shared/ui/toast";

const THEME_CYCLE: Theme[] = ["light", "dark", "system"];
const THEME_ICON = { light: Sun, dark: Moon, system: Monitor } as const;

export function Topbar() {
  const { t, locale, setLocale } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const theme = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const setPaletteOpen = useUiStore((state) => state.setPaletteOpen);

  const ThemeIcon = THEME_ICON[theme];
  const themeLabel = t(
    theme === "light" ? "nav.themeLight" : theme === "dark" ? "nav.themeDark" : "nav.themeSystem",
  );

  const logout = useApiMutation(mutations.logout, [], {
    onSuccess: () => {
      queryClient.clear();
      navigate("/login", { replace: true });
    },
    onError: (error) => toast.error(describeError(error, t)),
  });

  const cycleTheme = () => {
    const next = THEME_CYCLE[(THEME_CYCLE.indexOf(theme) + 1) % THEME_CYCLE.length];
    setTheme(next);
    void mutations.updateProfile({ theme: next }).then(
      () => queryClient.invalidateQueries({ queryKey: keys.session }),
      () => undefined,
    );
  };

  const switchLocale = () => {
    const next = locale === "ru" ? "en" : "ru";
    setLocale(next);
    void mutations.updateProfile({ locale: next }).then(
      () => queryClient.invalidateQueries({ queryKey: keys.session }),
      () => undefined,
    );
  };

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-app bg-surface px-4">
      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="flex h-8 w-full max-w-md items-center gap-2 rounded-md border border-app surface-muted px-2.5 text-left text-xs text-muted transition-colors hover:text-app"
      >
        <Search size={14} />
        <span className="flex-1 truncate">{t("search.placeholder")}</span>
        <kbd className="rounded border border-app px-1 py-px font-mono text-[0.65rem]">Ctrl K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={switchLocale}
          title={t("nav.language")}
          className="h-7 rounded-md px-2 text-xs font-medium text-muted uppercase transition-colors hover:bg-[rgb(var(--surface-muted))] hover:text-app"
        >
          {locale}
        </button>
        <IconButton label={themeLabel} onClick={cycleTheme}>
          <ThemeIcon size={15} />
        </IconButton>
        <div className="mx-1 h-5 w-px bg-[rgb(var(--border))]" />
        <div className="hidden text-right sm:block">
          <p className="text-xs font-medium leading-4">{session?.display_name}</p>
          <p className="text-[0.7rem] leading-4 text-muted">{session?.email}</p>
        </div>
        <IconButton label={t("nav.logout")} onClick={() => logout.mutate(undefined)}>
          <LogOut size={15} />
        </IconButton>
      </div>
    </header>
  );
}
