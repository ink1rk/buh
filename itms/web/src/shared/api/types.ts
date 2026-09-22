export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SessionUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  locale: string;
  theme: string;
  permissions: string[];
}

export interface LocationBrief {
  id: string;
  name: string;
  path: string;
  location_type: string;
}

export interface Ci {
  id: string;
  ci_type: string;
  code: string | null;
  name: string;
  status: string;
  criticality: string;
  environment: string;
  location_id: string | null;
  location: LocationBrief | null;
  owner_employee_id: string | null;
  vendor: string | null;
  model: string | null;
  serial_number: string | null;
  inventory_number: string | null;
  description: string | null;
  attributes: Record<string, unknown>;
  valid_from: string | null;
  valid_to: string | null;
  archived_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  tags: string[];
}

export interface RelatedItem {
  relation_id: string;
  rel_type: string;
  direction: "incoming" | "outgoing";
  criticality: string;
  description: string | null;
  ci: { id: string; name: string; code: string | null; ci_type: string; status: string };
}

export interface DocumentLinkRef {
  document_id: string;
  relation: string | null;
}

export type RelatedMap = Record<string, RelatedItem[] | DocumentLinkRef[]>;

export interface AuditChange {
  field: string;
  old_value: unknown;
  new_value: unknown;
}

export interface AuditLog {
  id: string;
  occurred_at: string;
  actor_id: string | null;
  actor_kind: string;
  actor_label: string | null;
  entity_type: string;
  entity_id: string | null;
  entity_label: string | null;
  action: string;
  change_id: string | null;
  project_id: string | null;
  task_id: string | null;
  document_id: string | null;
  reason: string | null;
  comment: string | null;
  source: string;
  changes: AuditChange[];
}

export interface ProvenanceEntry extends Omit<AuditLog, "id" | "changes" | "entity_type" | "entity_id" | "entity_label" | "comment"> {
  field: string;
  old_value: unknown;
  new_value: unknown;
}

export interface LocationNode {
  id: string;
  parent_id: string | null;
  location_type: string;
  name: string;
  code: string | null;
  path: string;
  depth: number;
  ci_count: number;
  children: LocationNode[];
}

export interface LocationRow {
  id: string;
  parent_id: string | null;
  location_type: string;
  name: string;
  code: string | null;
  path: string;
  depth: number;
  address: string | null;
  area_m2: number | null;
  responsible_employee_id: string | null;
  description: string | null;
  archived_at: string | null;
}

export interface Responsibility {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  color: string | null;
}

export interface Employee {
  id: string;
  full_name: string;
  position: string | null;
  email: string | null;
  phone: string | null;
  telegram: string | null;
  support_line: string;
  status: string;
  department_id: string | null;
  weekly_hours: number;
  notes: string | null;
  created_at: string;
  responsibilities: Array<{ id: string; name: string; color: string | null }>;
}

export interface WorkloadRow {
  id: string;
  full_name: string;
  status: string;
  owned_ci: number;
}

export interface DocumentSummary {
  id: string;
  title: string;
  kind: string;
  status: string;
  summary: string | null;
  folder_id: string | null;
  owner_employee_id: string | null;
  current_version: number;
  reviewed_on: string | null;
  review_due_on: string | null;
  review_period_days: number | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  content: string | null;
  content_format: string | null;
  links: Array<{
    id: string;
    document_id: string;
    entity_type: string;
    entity_id: string;
    relation: string | null;
  }>;
}

export interface DocumentVersion {
  id: string;
  version: number;
  title: string;
  content_format: string;
  change_note: string | null;
  created_at: string;
  created_by: string | null;
  is_current: boolean;
}

export interface SearchHit {
  entity_type: string;
  entity_id: string;
  title: string;
  subtitle: string | null;
  snippet: string | null;
  rank: number;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  counts: Record<string, number>;
}

export interface Dashboard {
  counters: {
    ci_total: number;
    ci_critical: number;
    ci_attention: number;
    locations: number;
    employees_active: number;
    documents: number;
    documents_review_due: number;
  };
  ci_by_type: Array<{ key: string; count: number }>;
  ci_by_status: Array<{ key: string; count: number }>;
  ci_by_criticality: Array<{ key: string; count: number }>;
  data_quality: {
    provenance: {
      changes_total: number;
      changes_with_provenance: number;
      coverage_pct: number;
    };
    ci_without_location: number;
    ci_without_owner: number;
  };
  recent_activity: Array<{
    id: string;
    occurred_at: string;
    actor_label: string | null;
    entity_type: string;
    entity_id: string | null;
    entity_label: string | null;
    action: string;
    reason: string | null;
  }>;
}

export interface Meta {
  ci_types: string[];
  ci_statuses: string[];
  ci_status_transitions: Record<string, string[]>;
  criticalities: string[];
  environments: string[];
  location_types: string[];
  location_parents: Record<string, string[]>;
  relation_types: string[];
  document_kinds: string[];
  document_statuses: string[];
  employee_statuses: string[];
  support_lines: string[];
  user_roles: string[];
  audit_actions: string[];
  import_targets: string[];
  import_fields: Record<string, string[]>;
  import_required_fields: Record<string, string[]>;
  power_defaults: Record<string, number>;
}

export interface ImportJob {
  id: string;
  target: string;
  status: string;
  filename: string;
  columns: string[];
  mapping: Record<string, string>;
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  rows_created: number;
  rows_updated: number;
  errors: Array<{ row: number; errors: string[] }>;
  preview: Array<Record<string, string>>;
  created_at: string;
  applied_at: string | null;
}
