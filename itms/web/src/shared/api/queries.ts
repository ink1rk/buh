import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
} from "@tanstack/react-query";

import { api, type Provenance } from "./client";
import type {
  AuditLog,
  CableRoute,
  Ci,
  ConnectionResult,
  ConnectionRow,
  Dashboard,
  Device,
  DeviceModel,
  DeviceRow,
  DiagramFull,
  DiagramNode,
  DiagramSummary,
  FloorplanSummary,
  FloorplanView,
  RackElevation,
  RackSummary,
  PowerOverview,
  AnalyticsReport,
  InboxItem,
  NotificationList,
  SavedView,
  ProjectSummary,
  ProjectView,
  TaskWork,
  DocumentDetail,
  DocumentSummary,
  DocumentVersion,
  Employee,
  FreePortsRow,
  ImportJob,
  InterfaceRow,
  IpAddress,
  IpAddressRow,
  LocationNode,
  LocationRow,
  Manufacturer,
  Meta,
  Page,
  PortUsage,
  PrefixDetail,
  PrefixRow,
  ProvenanceEntry,
  RedundancyGroup,
  RelatedMap,
  Responsibility,
  SearchResponse,
  SessionUser,
  TraceResult,
  TransitionView,
  VlanRow,
  Vrf,
  VirtOverview,
  WarrantyRow,
  WorkloadRow,
} from "./types";

export const keys = {
  session: ["session"] as const,
  meta: ["meta"] as const,
  dashboard: ["dashboard"] as const,
  ciList: (params: unknown) => ["ci", "list", params] as const,
  ci: (id: string) => ["ci", id] as const,
  ciRelated: (id: string) => ["ci", id, "related"] as const,
  ciHistory: (id: string) => ["ci", id, "history"] as const,
  ciDocuments: (id: string) => ["ci", id, "documents"] as const,
  ciProvenance: (id: string, field: string) => ["ci", id, "provenance", field] as const,
  locations: ["locations"] as const,
  locationTree: ["locations", "tree"] as const,
  employees: ["employees"] as const,
  responsibilities: ["responsibilities"] as const,
  workload: ["workload"] as const,
  documents: (params: unknown) => ["documents", "list", params] as const,
  document: (id: string) => ["documents", id] as const,
  documentVersions: (id: string) => ["documents", id, "versions"] as const,
  audit: (params: unknown) => ["audit", params] as const,
  search: (q: string) => ["search", q] as const,
  importJob: (id: string) => ["imports", id] as const,
  manufacturers: ["catalog", "manufacturers"] as const,
  models: (params: unknown) => ["catalog", "models", params] as const,
  model: (id: string) => ["catalog", "models", id] as const,
  devices: (params: unknown) => ["devices", "list", params] as const,
  device: (id: string) => ["devices", id] as const,
  deviceInterfaces: (id: string) => ["devices", id, "interfaces"] as const,
  devicePorts: (id: string) => ["devices", id, "ports"] as const,
  warranty: (days: number) => ["devices", "warranty", days] as const,
  connections: (params: unknown) => ["network", "connections", params] as const,
  trace: (id: string) => ["network", "trace", id] as const,
  routes: ["network", "routes"] as const,
  freePorts: ["network", "free-ports"] as const,
  redundancy: ["network", "redundancy"] as const,
  vrfs: ["ipam", "vrfs"] as const,
  vlans: (params: unknown) => ["ipam", "vlans", params] as const,
  prefixes: (params: unknown) => ["ipam", "prefixes", params] as const,
  prefix: (id: string) => ["ipam", "prefixes", id] as const,
  addresses: (params: unknown) => ["ipam", "addresses", params] as const,
  diagrams: ["diagrams"] as const,
  diagram: (id: string) => ["diagrams", id] as const,
  floorplans: ["floorplans"] as const,
  floorplan: (id: string) => ["floorplans", id] as const,
  racks: ["racks"] as const,
  rack: (id: string) => ["racks", id] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  inbox: ["projects", "inbox"] as const,
  notifications: ["notifications"] as const,
  analytics: ["projects", "analytics"] as const,
  views: ["projects", "views"] as const,
  taskWork: (projectId: string, taskId: string) => ["projects", projectId, "work", taskId] as const,
  power: ["power"] as const,
  virtualization: ["virtualization"] as const,
  transition: (id: string) => ["projects", id, "transition"] as const,
};

export function useSession() {
  return useQuery({
    queryKey: keys.session,
    queryFn: () => api.get<SessionUser>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
}

export function useMeta() {
  return useQuery({
    queryKey: keys.meta,
    queryFn: () => api.get<Meta>("/meta"),
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export function useDashboard() {
  return useQuery({
    queryKey: keys.dashboard,
    queryFn: () => api.get<Dashboard>("/dashboard"),
    refetchInterval: 60_000,
  });
}

export interface CiListParams {
  q?: string;
  ci_type?: string[];
  status?: string[];
  location_id?: string;
  owner_employee_id?: string;
  tag?: string[];
  criticality?: string[];
  without_owner?: boolean;
  without_location?: boolean;
  archived?: boolean;
  sort?: string;
  limit: number;
  offset: number;
}

export function useCiList(params: CiListParams) {
  return useQuery({
    queryKey: keys.ciList(params),
    queryFn: () => api.get<Page<Ci>>("/ci", params),
    placeholderData: (previous) => previous,
  });
}

export function useCi(id: string | undefined) {
  return useQuery({
    queryKey: keys.ci(id ?? ""),
    queryFn: () => api.get<Ci>(`/ci/${id}`),
    enabled: Boolean(id),
  });
}

export function useCiRelated(id: string | undefined) {
  return useQuery({
    queryKey: keys.ciRelated(id ?? ""),
    queryFn: () => api.get<RelatedMap>(`/ci/${id}/related`),
    enabled: Boolean(id),
  });
}

export function useCiHistory(id: string | undefined) {
  return useQuery({
    queryKey: keys.ciHistory(id ?? ""),
    queryFn: () => api.get<AuditLog[]>(`/ci/${id}/history`),
    enabled: Boolean(id),
  });
}

export function useCiDocuments(id: string | undefined) {
  return useQuery({
    queryKey: keys.ciDocuments(id ?? ""),
    queryFn: () => api.get<DocumentSummary[]>(`/ci/${id}/documents`),
    enabled: Boolean(id),
  });
}

export function useCiProvenance(id: string | undefined, field: string | null) {
  return useQuery({
    queryKey: keys.ciProvenance(id ?? "", field ?? ""),
    queryFn: () => api.get<ProvenanceEntry[]>(`/ci/${id}/provenance`, { field }),
    enabled: Boolean(id && field),
  });
}

export function useLocations() {
  return useQuery({
    queryKey: keys.locations,
    queryFn: () => api.get<LocationRow[]>("/locations"),
  });
}

export function useLocationTree() {
  return useQuery({
    queryKey: keys.locationTree,
    queryFn: () => api.get<LocationNode[]>("/locations/tree"),
  });
}

export function useEmployees() {
  return useQuery({
    queryKey: keys.employees,
    queryFn: () => api.get<Employee[]>("/directory/employees"),
  });
}

export function useResponsibilities() {
  return useQuery({
    queryKey: keys.responsibilities,
    queryFn: () => api.get<Responsibility[]>("/directory/responsibilities"),
  });
}

export function useWorkload() {
  return useQuery({
    queryKey: keys.workload,
    queryFn: () => api.get<WorkloadRow[]>("/directory/workload"),
  });
}

export interface DocumentListParams {
  q?: string;
  status?: string[];
  review_due?: boolean;
  limit: number;
  offset: number;
}

export function useDocuments(params: DocumentListParams) {
  return useQuery({
    queryKey: keys.documents(params),
    queryFn: () => api.get<Page<DocumentSummary>>("/documents", params),
    placeholderData: (previous) => previous,
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: keys.document(id ?? ""),
    queryFn: () => api.get<DocumentDetail>(`/documents/${id}`),
    enabled: Boolean(id),
  });
}

export function useDocumentVersions(id: string | undefined) {
  return useQuery({
    queryKey: keys.documentVersions(id ?? ""),
    queryFn: () => api.get<DocumentVersion[]>(`/documents/${id}/versions`),
    enabled: Boolean(id),
  });
}

export interface AuditParams {
  entity_type?: string;
  action?: string[];
  field?: string;
  date_from?: string;
  date_to?: string;
  limit: number;
  offset: number;
}

export function useAudit(params: AuditParams) {
  return useQuery({
    queryKey: keys.audit(params),
    queryFn: () => api.get<Page<AuditLog>>("/audit", params),
    placeholderData: (previous) => previous,
  });
}

export function useSearch(query: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.search(query),
    queryFn: () => api.get<SearchResponse>("/search", { q: query, limit: 25 }),
    enabled: enabled && query.trim().length > 0,
  });
}

export function useImportJob(id: string | null) {
  return useQuery({
    queryKey: keys.importJob(id ?? ""),
    queryFn: () => api.get<ImportJob>(`/imports/${id}`),
    enabled: Boolean(id),
  });
}

export function useManufacturers() {
  return useQuery({
    queryKey: keys.manufacturers,
    queryFn: () => api.get<Manufacturer[]>("/catalog/manufacturers"),
  });
}

export interface ModelListParams {
  q?: string;
  manufacturer_id?: string;
  role?: string;
  limit: number;
  offset: number;
}

export function useDeviceModels(params: ModelListParams) {
  return useQuery({
    queryKey: keys.models(params),
    queryFn: () => api.get<Page<DeviceModel>>("/catalog/models", params),
    placeholderData: (previous) => previous,
  });
}

export interface DeviceListParams {
  q?: string;
  role?: string[];
  location_id?: string;
  warranty_days?: number;
  limit: number;
  offset: number;
}

export function useDevices(params: DeviceListParams) {
  return useQuery({
    queryKey: keys.devices(params),
    queryFn: () => api.get<Page<DeviceRow>>("/devices", params),
    placeholderData: (previous) => previous,
  });
}

/** У объекта может не быть инженерного профиля — 404 здесь ожидаем и не повторяем запрос. */
export function useDiagrams() {
  return useQuery({
    queryKey: keys.diagrams,
    queryFn: () => api.get<DiagramSummary[]>("/diagrams"),
  });
}

export function useDiagram(id: string | undefined) {
  return useQuery({
    queryKey: keys.diagram(id ?? ""),
    queryFn: () => api.get<DiagramFull>(`/diagrams/${id}`),
    enabled: Boolean(id),
  });
}

export function useFloorplans() {
  return useQuery({
    queryKey: keys.floorplans,
    queryFn: () => api.get<FloorplanSummary[]>("/floorplans"),
  });
}

export function useFloorplan(id: string | undefined) {
  return useQuery({
    queryKey: keys.floorplan(id ?? ""),
    queryFn: () => api.get<FloorplanView>(`/floorplans/${id}`),
    enabled: Boolean(id),
  });
}

export function usePower() {
  return useQuery({
    queryKey: keys.power,
    queryFn: () => api.get<PowerOverview>("/power"),
  });
}

export function useVirtualization() {
  return useQuery({
    queryKey: keys.virtualization,
    queryFn: () => api.get<VirtOverview>("/virtualization"),
  });
}

export function useAnalytics() {
  return useQuery({
    queryKey: keys.analytics,
    queryFn: () => api.get<AnalyticsReport>("/projects/analytics"),
  });
}

export function useSavedViews() {
  return useQuery({
    queryKey: keys.views,
    queryFn: () => api.get<SavedView[]>("/projects/views"),
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: keys.notifications,
    queryFn: () => api.get<NotificationList>("/notifications"),
    refetchInterval: 30_000,
  });
}

export function useInbox() {
  return useQuery({
    queryKey: keys.inbox,
    queryFn: () => api.get<InboxItem[]>("/projects/inbox"),
  });
}

export function useTaskWork(projectId: string | undefined, taskId: string | undefined) {
  return useQuery({
    queryKey: keys.taskWork(projectId ?? "", taskId ?? ""),
    queryFn: () => api.get<TaskWork>(`/projects/${projectId}/tasks/${taskId}/work`),
    enabled: Boolean(projectId && taskId),
  });
}

export function useProjects() {
  return useQuery({
    queryKey: keys.projects,
    queryFn: () => api.get<ProjectSummary[]>("/projects"),
  });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: keys.project(id ?? ""),
    queryFn: () => api.get<ProjectView>(`/projects/${id}`),
    enabled: Boolean(id),
  });
}

export function useTransition(id: string | undefined) {
  return useQuery({
    queryKey: keys.transition(id ?? ""),
    queryFn: () => api.get<TransitionView>(`/projects/${id}/transition`),
    enabled: Boolean(id),
  });
}

export function useRacks() {
  return useQuery({
    queryKey: keys.racks,
    queryFn: () => api.get<RackSummary[]>("/racks"),
  });
}

export function useRack(id: string | undefined) {
  return useQuery({
    queryKey: keys.rack(id ?? ""),
    queryFn: () => api.get<RackElevation>(`/racks/${id}`),
    enabled: Boolean(id),
  });
}

export function useDevice(id: string | undefined) {
  return useQuery({
    queryKey: keys.device(id ?? ""),
    queryFn: () => api.get<Device>(`/devices/${id}`),
    enabled: Boolean(id),
    retry: false,
  });
}

export function useDeviceInterfaces(id: string | undefined) {
  return useQuery({
    queryKey: keys.deviceInterfaces(id ?? ""),
    queryFn: () => api.get<InterfaceRow[]>(`/devices/${id}/interfaces`),
    enabled: Boolean(id),
  });
}

export function usePortUsage(id: string | undefined) {
  return useQuery({
    queryKey: keys.devicePorts(id ?? ""),
    queryFn: () => api.get<PortUsage>(`/devices/${id}/ports`),
    enabled: Boolean(id),
  });
}

export function useWarranty(days: number) {
  return useQuery({
    queryKey: keys.warranty(days),
    queryFn: () => api.get<WarrantyRow[]>("/devices/warranty", { days }),
  });
}

export interface ConnectionListParams {
  q?: string;
  ci_id?: string;
  status?: string[];
  limit: number;
  offset: number;
}

export function useConnections(params: ConnectionListParams) {
  return useQuery({
    queryKey: keys.connections(params),
    queryFn: () => api.get<Page<ConnectionRow>>("/network/connections", params),
    placeholderData: (previous) => previous,
  });
}

export function useTrace(interfaceId: string | null) {
  return useQuery({
    queryKey: keys.trace(interfaceId ?? ""),
    queryFn: () => api.get<TraceResult>(`/network/interfaces/${interfaceId}/trace`),
    enabled: Boolean(interfaceId),
  });
}

export function useRoutes() {
  return useQuery({ queryKey: keys.routes, queryFn: () => api.get<CableRoute[]>("/network/routes") });
}

export function useFreePorts() {
  return useQuery({
    queryKey: keys.freePorts,
    queryFn: () => api.get<FreePortsRow[]>("/network/reports/free-ports"),
  });
}

export function useRedundancy() {
  return useQuery({
    queryKey: keys.redundancy,
    queryFn: () => api.get<RedundancyGroup[]>("/network/reports/redundancy"),
  });
}

export function useVrfs() {
  return useQuery({ queryKey: keys.vrfs, queryFn: () => api.get<Vrf[]>("/ipam/vrfs") });
}

export function useVlans(params: { q?: string; site_id?: string }) {
  return useQuery({
    queryKey: keys.vlans(params),
    queryFn: () => api.get<VlanRow[]>("/ipam/vlans", params),
  });
}

export function usePrefixes(params: { q?: string; vrf_id?: string }) {
  return useQuery({
    queryKey: keys.prefixes(params),
    queryFn: () => api.get<PrefixRow[]>("/ipam/prefixes", params),
  });
}

export function usePrefix(id: string | null) {
  return useQuery({
    queryKey: keys.prefix(id ?? ""),
    queryFn: () => api.get<PrefixDetail>(`/ipam/prefixes/${id}`),
    enabled: Boolean(id),
  });
}

export interface AddressListParams {
  q?: string;
  ci_id?: string;
  prefix_id?: string;
  limit: number;
  offset: number;
}

export function useAddresses(params: AddressListParams) {
  return useQuery({
    queryKey: keys.addresses(params),
    queryFn: () => api.get<Page<IpAddressRow>>("/ipam/addresses", params),
    placeholderData: (previous) => previous,
  });
}

/**
 * Мутация, которая после успеха сбрасывает перечисленные ветки кэша.
 * Дашборд и история зависят почти от любой записи, поэтому инвалидация явная.
 */
export function useApiMutation<TData, TVariables>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  invalidate: Array<readonly unknown[]> = [],
  options: Omit<UseMutationOptions<TData, unknown, TVariables>, "mutationFn"> = {},
) {
  const queryClient = useQueryClient();
  return useMutation<TData, unknown, TVariables>({
    mutationFn,
    ...options,
    onSuccess: (...args) => {
      for (const key of invalidate) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
      options.onSuccess?.(...args);
    },
  });
}

export const mutations = {
  login: (body: { email: string; password: string }) => api.post<SessionUser>("/auth/login", body),
  logout: () => api.post<{ ok: boolean }>("/auth/logout"),
  updateProfile: (body: Record<string, unknown>) => api.patch<SessionUser>("/auth/me", body),
  readNotification: (id: string) => api.post<NotificationList>(`/notifications/${id}/read`),
  readNotifications: () => api.post<NotificationList>("/notifications/read"),
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<{ ok: boolean }>("/auth/password", body),

  createCi: (body: Record<string, unknown>, provenance?: Provenance) =>
    api.post<Ci>("/ci", body, provenance),
  updateCi: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<Ci>(`/ci/${id}`, body, provenance),
  archiveCi: (id: string, provenance?: Provenance) =>
    api.post<Ci>(`/ci/${id}/archive`, undefined, provenance),
  restoreCi: (id: string, provenance?: Provenance) =>
    api.post<Ci>(`/ci/${id}/restore`, undefined, provenance),
  deleteCi: (id: string, provenance?: Provenance) => api.delete<{ ok: boolean }>(`/ci/${id}`, provenance),

  createRelation: (body: Record<string, unknown>, provenance?: Provenance) =>
    api.post("/relations", body, provenance),
  deleteRelation: (id: string, provenance?: Provenance) =>
    api.delete<{ ok: boolean }>(`/relations/${id}`, provenance),

  createLocation: (body: Record<string, unknown>, provenance?: Provenance) =>
    api.post<LocationRow>("/locations", body, provenance),
  updateLocation: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<LocationRow>(`/locations/${id}`, body, provenance),
  archiveLocation: (id: string, provenance?: Provenance) =>
    api.post<LocationRow>(`/locations/${id}/archive`, undefined, provenance),

  createEmployee: (body: Record<string, unknown>) => api.post<Employee>("/directory/employees", body),
  updateEmployee: (id: string, body: Record<string, unknown>) =>
    api.patch<Employee>(`/directory/employees/${id}`, body),

  createDocument: (body: Record<string, unknown>, provenance?: Provenance) =>
    api.post<DocumentDetail>("/documents", body, provenance),
  updateDocument: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<DocumentDetail>(`/documents/${id}`, body, provenance),
  restoreDocumentVersion: (id: string, version: number, provenance?: Provenance) =>
    api.post<DocumentDetail>(`/documents/${id}/versions/${version}/restore`, undefined, provenance),
  linkDocument: (id: string, body: Record<string, unknown>) =>
    api.post(`/documents/${id}/links`, body),
  unlinkDocument: (linkId: string) => api.delete<{ ok: boolean }>(`/documents/links/${linkId}`),
  archiveDocument: (id: string, provenance?: Provenance) =>
    api.post<DocumentSummary>(`/documents/${id}/archive`, undefined, provenance),

  createImport: (target: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.upload<ImportJob>("/imports", form, { target });
  },
  updateImportMapping: (id: string, mapping: Record<string, string>) =>
    api.patch<ImportJob>(`/imports/${id}/mapping`, { mapping }),
  validateImport: (id: string) => api.post<ImportJob>(`/imports/${id}/validate`),
  applyImport: (id: string) => api.post<ImportJob>(`/imports/${id}/apply`),

  createUser: (body: Record<string, unknown>) =>
    api.post<{
      id: string;
      email: string;
      display_name: string;
      role: string;
      status: string;
      last_login_at: string | null;
    }>("/users", body),
  updateUser: (
    id: string,
    body: Record<string, unknown>,
    provenance?: Provenance,
  ) =>
    api.patch<{
      id: string;
      email: string;
      display_name: string;
      role: string;
      status: string;
      last_login_at: string | null;
    }>(`/users/${id}`, body, provenance),
  installBlueprints: () =>
    api.post<{
      nodes_created: number;
      nodes_skipped: number;
      links_created: number;
      links_skipped: number;
    }>("/catalog/blueprints"),
  installCatalogLibrary: () =>
    api.post<{
      manufacturers_created: number;
      manufacturers_skipped: number;
      models_created: number;
      models_skipped: number;
    }>("/catalog/library"),
  createManufacturer: (body: Record<string, unknown>) =>
    api.post<Manufacturer>("/catalog/manufacturers", body),
  updateManufacturer: (id: string, body: Record<string, unknown>) =>
    api.patch<Manufacturer>(`/catalog/manufacturers/${id}`, body),
  createModel: (body: Record<string, unknown>) => api.post<DeviceModel>("/catalog/models", body),
  updateModel: (id: string, body: Record<string, unknown>) =>
    api.patch<DeviceModel>(`/catalog/models/${id}`, body),
  deleteModel: (id: string) => api.delete<{ ok: boolean }>(`/catalog/models/${id}`),
  addPortTemplate: (modelId: string, body: Record<string, unknown>) =>
    api.post(`/catalog/models/${modelId}/port-templates`, body),
  deletePortTemplate: (id: string) => api.delete<{ ok: boolean }>(`/catalog/port-templates/${id}`),

  saveDevice: (ciId: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.put<Device>(`/devices/${ciId}`, body, provenance),
  createInterface: (ciId: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.post<InterfaceRow[]>(`/devices/${ciId}/interfaces`, body, provenance),
  createInterfacesFromModel: (ciId: string) =>
    api.post<InterfaceRow[]>(`/devices/${ciId}/interfaces/from-model`),
  updateInterface: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<InterfaceRow>(`/interfaces/${id}`, body, provenance),
  deleteInterface: (id: string, provenance?: Provenance) =>
    api.delete<{ ok: boolean }>(`/interfaces/${id}`, provenance),

  createConnection: (body: Record<string, unknown>, provenance?: Provenance) =>
    api.post<ConnectionResult>("/network/connections", body, provenance),
  updateConnection: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<ConnectionResult>(`/network/connections/${id}`, body, provenance),
  deleteConnection: (id: string, provenance?: Provenance) =>
    api.delete<{ ok: boolean }>(`/network/connections/${id}`, provenance),
  createRoute: (body: Record<string, unknown>) => api.post<CableRoute>("/network/routes", body),

  createVlan: (body: Record<string, unknown>) => api.post<VlanRow>("/ipam/vlans", body),
  updateVlan: (id: string, body: Record<string, unknown>) =>
    api.patch<VlanRow>(`/ipam/vlans/${id}`, body),
  createPrefix: (body: Record<string, unknown>) => api.post<PrefixRow>("/ipam/prefixes", body),
  updatePrefix: (id: string, body: Record<string, unknown>) =>
    api.patch<PrefixRow>(`/ipam/prefixes/${id}`, body),
  createAddress: (body: Record<string, unknown>) => api.post<IpAddress>("/ipam/addresses", body),
  updateAddress: (id: string, body: Record<string, unknown>) =>
    api.patch<IpAddress>(`/ipam/addresses/${id}`, body),
  deleteAddress: (id: string) => api.delete<{ ok: boolean }>(`/ipam/addresses/${id}`),

  createDiagram: (body: Record<string, unknown>) => api.post<DiagramSummary>("/diagrams", body),
  updateDiagram: (id: string, body: Record<string, unknown>) =>
    api.patch<DiagramSummary>(`/diagrams/${id}`, body),
  deleteDiagram: (id: string) => api.delete<{ ok: boolean }>(`/diagrams/${id}`),
  saveDiagramLayout: (
    id: string,
    body: {
      version: number;
      nodes: Array<{ id: string; x: number; y: number }>;
      viewport?: { x: number; y: number; zoom: number };
    },
  ) => api.patch<DiagramSummary>(`/diagrams/${id}/layout`, body),
  addDiagramNode: (id: string, ciId: string) =>
    api.post<DiagramNode>(`/diagrams/${id}/nodes`, { ci_id: ciId }),
  removeDiagramNode: (nodeId: string) => api.delete<{ ok: boolean }>(`/diagrams/nodes/${nodeId}`),
  syncDiagram: (id: string) => api.post<DiagramFull>(`/diagrams/${id}/sync`),
  autolayoutDiagram: (id: string) => api.post<DiagramFull>(`/diagrams/${id}/autolayout`),

  createHost: (body: Record<string, unknown>) =>
    api.post<VirtOverview>("/virtualization/hosts", body),
  updateHost: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<VirtOverview>(`/virtualization/hosts/${id}`, body, provenance),
  createVm: (body: Record<string, unknown>) => api.post<VirtOverview>("/virtualization/vms", body),
  updateVm: (id: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.patch<VirtOverview>(`/virtualization/vms/${id}`, body, provenance),

  createPowerNode: (body: Record<string, unknown>) =>
    api.post<{ id: string }>("/power/nodes", body),
  createPowerLink: (body: Record<string, unknown>) =>
    api.post<{ id: string }>("/power/links", body),

  createProject: (body: Record<string, unknown>) => api.post<ProjectView>("/projects", body),
  createFromTemplate: (body: Record<string, unknown>) =>
    api.post<ProjectView>("/projects/from-template", body),
  addRecurrence: (id: string, body: Record<string, unknown>) =>
    api.post<unknown>(`/projects/${id}/recurrences`, body),
  saveView: (body: Record<string, unknown>) => api.post<SavedView[]>("/projects/views", body),
  updateProject: (id: string, body: Record<string, unknown>) =>
    api.patch<ProjectView>(`/projects/${id}`, body),
  addPhase: (id: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/phases`, body),
  addMilestone: (id: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/milestones`, body),
  addTask: (id: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/tasks`, body),
  updateTask: (id: string, taskId: string, body: Record<string, unknown>) =>
    api.patch<ProjectView>(`/projects/${id}/tasks/${taskId}`, body),
  addComment: (id: string, taskId: string, body: string) =>
    api.post<TaskWork>(`/projects/${id}/tasks/${taskId}/comments`, { body }),
  addCheck: (id: string, taskId: string, title: string) =>
    api.post<TaskWork>(`/projects/${id}/tasks/${taskId}/checks`, { title }),
  updateCheck: (id: string, taskId: string, checkId: string, done: boolean) =>
    api.patch<TaskWork>(`/projects/${id}/tasks/${taskId}/checks/${checkId}`, { done }),
  addDependency: (id: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/dependencies`, body),
  linkProjectCi: (id: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/ci`, body),
  unlinkProjectCi: (id: string, ciId: string) =>
    api.delete<ProjectView>(`/projects/${id}/ci/${ciId}`),
  addMember: (id: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/members`, body),
  addTime: (id: string, taskId: string, body: Record<string, unknown>) =>
    api.post<ProjectView>(`/projects/${id}/tasks/${taskId}/time`, body),
  takeSnapshot: (id: string, name: string) =>
    api.post(`/projects/${id}/snapshots`, { name }),
  buildPlan: (id: string) => api.post<TransitionView>(`/projects/${id}/plans`),
  applyPlan: (id: string, planId: string, provenance?: Provenance) =>
    api.post<TransitionView>(`/projects/${id}/plans/${planId}/apply`, undefined, provenance),
  rollbackPlan: (id: string, planId: string, provenance?: Provenance) =>
    api.post<TransitionView>(`/projects/${id}/plans/${planId}/rollback`, undefined, provenance),

  createFloorplan: (body: Record<string, unknown>) =>
    api.post<FloorplanView>("/floorplans", body),
  placeFloorplanItem: (planId: string, body: Record<string, unknown>) =>
    api.post<FloorplanView>(`/floorplans/${planId}/items`, body),
  moveFloorplanItem: (planId: string, itemId: string, body: Record<string, unknown>) =>
    api.patch<FloorplanView>(`/floorplans/${planId}/items/${itemId}`, body),

  createRack: (body: Record<string, unknown>) => api.post<RackElevation>("/racks", body),
  placeMount: (rackId: string, body: Record<string, unknown>, provenance?: Provenance) =>
    api.put<RackElevation>(`/racks/${rackId}/mounts`, body, provenance),
  removeMount: (rackId: string, mountId: string, toStock: boolean, provenance?: Provenance) =>
    api.delete<RackElevation>(`/racks/${rackId}/mounts/${mountId}?to_stock=${toStock}`, provenance),
};
