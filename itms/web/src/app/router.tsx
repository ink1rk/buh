import { createBrowserRouter, Navigate } from "react-router-dom";

import { AuditPage } from "@/features/audit/AuditPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { CatalogPage } from "@/features/catalog/CatalogPage";
import { CiDetailPage } from "@/features/ci/CiDetailPage";
import { CiListPage } from "@/features/ci/CiListPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { DiagramEditorPage } from "@/features/diagrams/DiagramEditorPage";
import { DiagramsPage } from "@/features/diagrams/DiagramsPage";
import { DevicesPage } from "@/features/devices/DevicesPage";
import { DirectoryPage } from "@/features/directory/DirectoryPage";
import { DocumentDetailPage } from "@/features/documents/DocumentDetailPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { FloorplanPage } from "@/features/floorplans/FloorplanPage";
import { FloorplansPage } from "@/features/floorplans/FloorplansPage";
import { DatacenterPage } from "@/features/infrastructure/DatacenterPage";
import { InfraFrame } from "@/features/infrastructure/InfraFrame";
import { InfrastructurePage } from "@/features/infrastructure/InfrastructurePage";
import { ImportPage } from "@/features/imports/ImportPage";
import { IpamPage } from "@/features/ipam/IpamPage";
import { LocationsPage } from "@/features/locations/LocationsPage";
import { PowerPage } from "@/features/power/PowerPage";
import { AnalyticsPage } from "@/features/projects/AnalyticsPage";
import { ProjectPage } from "@/features/projects/ProjectPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { RackEditorPage } from "@/features/racks/RackEditorPage";
import { RacksPage } from "@/features/racks/RacksPage";
import { NetworkPage } from "@/features/network/NetworkPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { VirtualizationPage } from "@/features/virtualization/VirtualizationPage";
import { WorkPage } from "@/features/work/WorkPage";

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
      { path: "/work", element: <WorkPage /> },
      { path: "/ci/:ciId", element: <CiDetailPage /> },
      { path: "/diagrams/:diagramId", element: <DiagramEditorPage /> },
      { path: "/racks/:rackId", element: <RackEditorPage /> },
      { path: "/floorplans/:planId", element: <FloorplanPage /> },
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/analytics", element: <AnalyticsPage /> },
      { path: "/projects/:projectId", element: <ProjectPage /> },
      {
        element: <InfraFrame />,
        children: [
          { path: "/infrastructure", element: <InfrastructurePage /> },
          { path: "/datacenter", element: <DatacenterPage /> },
          { path: "/ci", element: <CiListPage /> },
          { path: "/devices", element: <DevicesPage /> },
          { path: "/network", element: <NetworkPage /> },
          { path: "/ipam", element: <IpamPage /> },
          { path: "/diagrams", element: <DiagramsPage /> },
          { path: "/racks", element: <RacksPage /> },
          { path: "/floorplans", element: <FloorplansPage /> },
          { path: "/locations", element: <LocationsPage /> },
          { path: "/power", element: <PowerPage /> },
          { path: "/virtualization", element: <VirtualizationPage /> },
        ],
      },
      { path: "/catalog", element: <CatalogPage /> },
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
