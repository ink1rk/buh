import { Outlet } from "react-router-dom";

import { CommandPalette } from "@/features/search/CommandPalette";
import { useHotkey } from "@/shared/hooks";
import { useUiStore } from "@/shared/store/ui";

import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  const setPaletteOpen = useUiStore((state) => state.setPaletteOpen);
  const toggleNav = useUiStore((state) => state.toggleNav);

  useHotkey("k", () => setPaletteOpen(true), { ctrl: true, allowInInput: true });
  useHotkey("b", toggleNav, { ctrl: true });

  return (
    <div className="flex h-full bg-app">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-5">
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
