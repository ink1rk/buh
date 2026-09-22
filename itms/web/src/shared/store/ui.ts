import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark" | "system";
export type Locale = "ru" | "en";

interface UiState {
  theme: Theme;
  locale: Locale;
  navCollapsed: boolean;
  paletteOpen: boolean;
  recent: Array<{ id: string; title: string; path: string }>;
  setTheme: (theme: Theme) => void;
  setLocale: (locale: Locale) => void;
  toggleNav: () => void;
  setPaletteOpen: (open: boolean) => void;
  pushRecent: (item: { id: string; title: string; path: string }) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: "dark",
      locale: "ru",
      navCollapsed: false,
      paletteOpen: false,
      recent: [],
      setTheme: (theme) => set({ theme }),
      setLocale: (locale) => set({ locale }),
      toggleNav: () => set((state) => ({ navCollapsed: !state.navCollapsed })),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      pushRecent: (item) =>
        set((state) => ({
          recent: [item, ...state.recent.filter((entry) => entry.id !== item.id)].slice(0, 12),
        })),
    }),
    {
      name: "itms-ui",
      partialize: (state) => ({
        theme: state.theme,
        locale: state.locale,
        navCollapsed: state.navCollapsed,
        recent: state.recent,
      }),
    },
  ),
);

export function applyTheme(theme: Theme): void {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = theme === "dark" || (theme === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", dark);
}
