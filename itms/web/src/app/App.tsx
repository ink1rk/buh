import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { RouterProvider } from "react-router-dom";

import { I18nProvider } from "@/i18n";
import { ApiError } from "@/shared/api/client";
import { applyTheme, useUiStore } from "@/shared/store/ui";
import { ToastViewport } from "@/shared/ui/toast";

import { router } from "./router";

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        // 401 означает «нужно войти», повторять такой запрос бессмысленно.
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status < 500) && failureCount < 2,
      },
    },
  });
}

export function App() {
  const [queryClient] = useState(createQueryClient);
  const theme = useUiStore((state) => state.theme);

  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <RouterProvider router={router} />
        <ToastViewport />
      </I18nProvider>
    </QueryClientProvider>
  );
}
