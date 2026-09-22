import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
} from "@tanstack/react-query";

import { api, type Provenance } from "./client";
import type {
  AuditLog,
  Ci,
  Dashboard,
  DocumentDetail,
  DocumentSummary,
  DocumentVersion,
  Employee,
  ImportJob,
  LocationNode,
  LocationRow,
  Meta,
  Page,
  ProvenanceEntry,
  RelatedMap,
  Responsibility,
  SearchResponse,
  SessionUser,
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
};
