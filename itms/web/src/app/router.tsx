import { createBrowserRouter, Navigate } from "react-router-dom";

import { AuditPage } from "@/features/audit/AuditPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { CatalogPage } from "@/features/catalog/CatalogPage";
import { CiDetailPage } from "@/features/ci/CiDetailPage";
import { CiListPage } from "@/features/ci/CiListPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { DevicesPage } from "@/features/devices/DevicesPage";
import { DirectoryPage } from "@/features/directory/DirectoryPage";
import { DocumentDetailPage } from "@/features/documents/DocumentDetailPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { ImportPage } from "@/features/imports/ImportPage";
import { IpamPage } from "@/features/ipam/IpamPage";
import { LocationsPage } from "@/features/locations/LocationsPage";
import { NetworkPage } from "@/features/network/NetworkPage";
import { SettingsPage } from "@/features/settings/SettingsPage";

import { AppShell } from "./layout/AppShell";
import { RequireAuth } from "./RequireAuth";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { path: "/", element: <Navigate to="/dashboard" replace /> },
      { path: "/dashboard", element: <DashboardPage /> },
      { path: "/ci", element: <CiListPage /> },
      { path: "/ci/:ciId", element: <CiDetailPage /> },
      { path: "/devices", element: <DevicesPage /> },
      { path: "/network", element: <NetworkPage /> },
      { path: "/ipam", element: <IpamPage /> },
      { path: "/catalog", element: <CatalogPage /> },
      { path: "/locations", element: <LocationsPage /> },
      { path: "/documents", element: <DocumentsPage /> },
      { path: "/documents/:documentId", element: <DocumentDetailPage /> },
      { path: "/directory", element: <DirectoryPage /> },
      { path: "/audit", element: <AuditPage /> },
      { path: "/imports", element: <ImportPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "*", element: <Navigate to="/dashboard" replace /> },
    ],
  },
]);
