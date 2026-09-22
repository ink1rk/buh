import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useSession } from "@/shared/api/queries";
import { Spinner } from "@/shared/ui/Layout";

export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { data, isPending, isError } = useSession();

  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (isError || !data) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
