import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { NotificationBell } from "@/features/projects/NotificationBell";
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

  const initials = (session?.display_name ?? session?.email ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-app bg-[rgb(var(--surface)/0.86)] px-4 backdrop-blur-md sm:px-5">
      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="flex h-9 w-full max-w-lg items-center gap-2 rounded-xl border border-app bg-[rgb(var(--surface-muted))] px-3 text-left text-sm text-muted transition-colors hover:text-app"
      >
        <Search size={15} strokeWidth={1.75} />
        <span className="flex-1 truncate">{t("search.placeholder")}</span>
        <kbd className="rounded-md border border-app bg-[rgb(var(--surface))] px-1.5 py-0.5 font-mono text-[0.65rem]">
          Ctrl K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          onClick={switchLocale}
          title={t("nav.language")}
          className="h-8 rounded-lg px-2 text-xs font-semibold tracking-wide text-muted uppercase transition-colors hover:bg-[rgb(var(--surface-muted))] hover:text-app"
        >
          {locale}
        </button>
        <NotificationBell />
        <IconButton label={themeLabel} onClick={cycleTheme}>
          <ThemeIcon size={16} strokeWidth={1.75} />
        </IconButton>
        <div className="mx-1.5 hidden h-6 w-px bg-[rgb(var(--border))] sm:block" />
        <div className="hidden items-center gap-2 sm:flex">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[rgb(var(--accent-soft))] text-[0.7rem] font-semibold text-[rgb(var(--accent))]">
            {initials}
          </span>
          <div className="text-right">
            <p className="text-xs leading-4 font-semibold">{session?.display_name}</p>
            <p className="text-[0.68rem] leading-4 text-muted">{session?.email}</p>
          </div>
        </div>
        <IconButton label={t("nav.logout")} onClick={() => logout.mutate(undefined)}>
          <LogOut size={16} strokeWidth={1.75} />
        </IconButton>
      </div>
    </header>
  );
}
