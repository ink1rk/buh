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
    project_id?: string | null;
    changes?: Array<{ field: string; old_value: string | null; new_value: string | null }>;
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
  device_roles: string[];
  interface_types: string[];
  cable_media: string[];
  cable_categories: string[];
  connection_statuses: string[];
  vlan_modes: string[];
  ip_statuses: string[];
  ip_roles: string[];
  panel_sides: string[];
  power_defaults: Record<string, number>;
}

export interface Manufacturer {
  id: string;
  name: string;
  support_url: string | null;
  notes: string | null;
}

export interface PortTemplate {
  id: string;
  name_pattern: string;
  count: number;
  start_index: number;
  interface_type: string;
  speed_mbps: number | null;
  poe_capable: boolean;
  position: number;
}

export interface DeviceModel {
  id: string;
  manufacturer_id: string;
  manufacturer: Manufacturer;
  model: string;
  part_number: string | null;
  default_role: string;
  u_height: number;
  is_full_depth: boolean;
  depth_mm: number | null;
  weight_kg: number | null;
  psu_count: number;
  power_nameplate_w: number | null;
  power_max_w: number | null;
  power_factor: number | null;
  utilization_factor: number | null;
  airflow: string | null;
  notes: string | null;
  port_templates: PortTemplate[];
}

export interface Device {
  id: string;
  device_model_id: string | null;
  model: DeviceModel | null;
  device_role: string;
  asset_tag: string | null;
  hostname: string | null;
  mgmt_ip: string | null;
  mgmt_mac: string | null;
  firmware: string | null;
  os_version: string | null;
  purchase_date: string | null;
  warranty_until: string | null;
  psu_count: number;
  power_nameplate_w: number | null;
  power_max_w: number | null;
  notes: string | null;
}

export interface DeviceRow {
  id: string;
  name: string;
  code: string | null;
  status: string;
  criticality: string;
  location_id: string | null;
  device_role: string;
  hostname: string | null;
  mgmt_ip: string | null;
  serial_number: string | null;
  asset_tag: string | null;
  warranty_until: string | null;
  model_label: string | null;
}

export interface PortUsage {
  total: number;
  free: number;
  used: number;
}

export interface EndpointRef {
  interface_id: string;
  interface_name: string;
  ci_id: string;
  ci_name: string | null;
}

export interface ConnectionBrief {
  id: string;
  label: string | null;
  status: string;
  medium: string;
  length_m: number | null;
  peer: EndpointRef | null;
}

export interface InterfaceRow {
  id: string;
  ci_id: string;
  name: string;
  position: number | null;
  interface_type: string;
  medium: string | null;
  speed_mbps: number | null;
  mac: string | null;
  description: string;
  purpose: string | null;
  admin_enabled: boolean;
  oper_status: string;
  is_management: boolean;
  mtu: number | null;
  panel_side: string | null;
  paired_interface_id: string | null;
  lag_parent_id: string | null;
  ip_addresses: string[];
  vlans: Array<{ vlan_id: string; vid: number; name: string; mode: string }>;
  connection: ConnectionBrief | null;
}

export interface ConnectionRow {
  id: string;
  label: string | null;
  medium: string;
  category: string | null;
  status: string;
  length_m: number | null;
  speed_mbps: number | null;
  color: string | null;
  is_redundant: boolean;
  redundancy_group: string | null;
  route_id: string | null;
  installed_on: string | null;
  description: string;
  a_end: EndpointRef | null;
  b_end: EndpointRef | null;
}

export interface ConnectionResult {
  connection: ConnectionRow;
  warnings: string[];
}

export interface TraceResult {
  start: EndpointRef;
  endpoint: EndpointRef | null;
  segments: Array<{ connection_id: string; label: string | null; length_m: number | null }>;
  passed_through: Array<{ ci_id: string; ci_name: string | null }>;
  total_length_m: number | null;
  is_direct: boolean;
  truncated: boolean;
}

export interface RedundancyGroup {
  group: string;
  members: Array<{ id: string; label: string | null; status: string }>;
  issues: string[];
}

export interface FreePortsRow {
  ci_id: string;
  name: string;
  device_role: string;
  total: number;
  free: number;
}

export interface CableRoute {
  id: string;
  name: string;
  route_type: string | null;
  from_location_id: string | null;
  to_location_id: string | null;
  length_m: number | null;
  capacity: number | null;
  notes: string | null;
}

export interface Vrf {
  id: string;
  name: string;
  rd: string | null;
  description: string | null;
}

export interface VlanRow {
  id: string;
  vid: number;
  name: string;
  site_id: string | null;
  site_name: string | null;
  purpose: string | null;
  description: string | null;
  prefix_count: number;
}

export interface PrefixRow {
  id: string;
  cidr: string;
  version: number;
  vrf_id: string | null;
  vrf_name: string | null;
  vlan_id: string | null;
  vlan_label: string | null;
  gateway: string | null;
  site_id: string | null;
  description: string | null;
  usable_total: number;
  used: number;
  free: number;
  utilisation_pct: number;
}

export interface IpAddressRow {
  id: string;
  address: string;
  prefix_id: string | null;
  vrf_id: string | null;
  interface_id: string | null;
  interface_name: string | null;
  ci_id: string | null;
  ci_name: string | null;
  dns_name: string | null;
  role: string;
  status: string;
  description: string | null;
}

export interface IpAddress {
  id: string;
  address: string;
  vrf_id: string | null;
  prefix_id: string | null;
  interface_id: string | null;
  ci_id: string | null;
  dns_name: string | null;
  role: string;
  status: string;
  description: string | null;
  created_at: string;
}

export interface PrefixDetail {
  prefix: PrefixRow;
  capacity: {
    usable_total: number;
    used: number;
    free: number;
    utilisation_pct: number;
    network_address: string;
    broadcast_address: string | null;
    netmask: string;
  };
  next_free: string[];
  addresses: IpAddressRow[];
}

export interface WarrantyRow {
  id: string;
  name: string;
  warranty_until: string;
  device_role: string;
}

export interface DiagramSummary {
  id: string;
  name: string;
  diagram_type: string;
  location_id: string | null;
  description: string | null;
  viewport: { x?: number; y?: number; zoom?: number };
  version: number;
}

export interface DiagramNode {
  id: string;
  ci_id: string | null;
  node_kind: string;
  x: number;
  y: number;
  label: string;
  code: string | null;
  ci_type: string | null;
  status: string | null;
  criticality: string | null;
  device_role: string | null;
  hostname: string | null;
  mgmt_ip: string | null;
  power_node_type: string | null;
  inlet_w: number | null;
  limit_w: number | null;
}

export interface DiagramEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  connection_id: string | null;
  relation_id: string | null;
  power_link_id: string | null;
  label: string | null;
  medium: string | null;
  status: string | null;
  length_m: number | null;
  is_redundant: boolean;
  redundancy_group: string | null;
  rel_type: string | null;
}

export interface DiagramFull {
  diagram: DiagramSummary;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export interface FloorplanSummary {
  id: string;
  name: string;
  location_id: string;
  location_name: string | null;
  width_mm: number;
  height_mm: number;
  item_count: number;
}

export interface FloorplanItem {
  id: string;
  ci_id: string | null;
  code: string | null;
  name: string;
  item_kind: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
}

export interface FloorplanCandidate {
  ci_id: string;
  code: string | null;
  name: string;
  item_kind: string;
  width: number;
  height: number;
}

export interface FloorplanView {
  plan: Omit<FloorplanSummary, "item_count">;
  items: FloorplanItem[];
  available: FloorplanCandidate[];
}

export interface RackSummary {
  id: string;
  name: string;
  code: string | null;
  location_id: string | null;
  location_path: string | null;
  u_height: number;
  form_factor: string;
  used_front: number;
  used_rear: number;
  largest_free_front: number;
  weight_kg: number;
  max_weight_kg: number | null;
  power_w: number;
  max_power_w: number | null;
}

export interface RackDetail {
  id: string;
  name: string;
  code: string | null;
  location_id: string | null;
  location_path: string | null;
  description: string | null;
  u_height: number;
  width_in: number;
  depth_mm: number;
  max_weight_kg: number | null;
  max_power_w: number | null;
  form_factor: string;
  descending_units: boolean;
}

export interface FreeBlock {
  start: number;
  length: number;
}

export interface RackMount {
  id: string;
  ci_id: string;
  name: string;
  code: string | null;
  status: string;
  device_role: string | null;
  position_u: number;
  u_height: number;
  face: string;
  zero_u_side: string | null;
  depth_mm: number | null;
  weight_kg: number | null;
  power_w: number | null;
  is_reservation: boolean;
}

export interface WarehouseItem {
  ci_id: string;
  name: string;
  code: string | null;
  status: string;
  device_role: string | null;
  u_height: number;
  power_w: number | null;
  weight_kg: number | null;
}

export interface RackCapacity {
  u_height: number;
  used_front: number;
  used_rear: number;
  weight_kg: number;
  max_weight_kg: number | null;
  power_w: number;
  max_power_w: number | null;
}

export interface RackElevation {
  rack: RackDetail;
  mounts: RackMount[];
  free_front: FreeBlock[];
  free_rear: FreeBlock[];
  capacity: RackCapacity;
  warehouse: WarehouseItem[];
}

export interface ProjectSummary {
  id: string;
  key: string;
  name: string;
  status: string;
  priority: string;
  owner_name: string | null;
  start_date: string | null;
  due_date: string | null;
  progress_pct: number;
  health: string;
  task_count: number;
  open_task_count: number;
}

export interface ProjectPhase {
  id: string;
  name: string;
  order_index: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
  progress_pct: number;
}

export interface ProjectMilestone {
  id: string;
  name: string;
  due_date: string | null;
  status: string;
  description: string;
  completed_at: string | null;
}

export interface NotificationItem {
  id: string;
  kind: string;
  title: string;
  body: string;
  project_id: string | null;
  task_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  unread: number;
  items: NotificationItem[];
}

export interface SavedView {
  id: string;
  name: string;
  project_id: string | null;
  status: string | null;
  priority: string | null;
  bucket: string | null;
}

export interface AnalyticsReport {
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  open: number;
  completed: number;
  overdue: number;
  workload: Array<{ name: string; open: number; estimate_min: number }>;
}

export interface InboxItem {
  id: string;
  project_id: string;
  project_key: string;
  project_name: string;
  label: string;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  assignee_name: string | null;
  bucket: string;
}

export interface TaskWork {
  comments: Array<{ id: string; body: string; author_label: string; created_at: string }>;
  checks: Array<{ id: string; title: string; done: boolean }>;
}

export interface ProjectTask {
  id: string;
  number: number;
  label: string;
  title: string;
  description: string;
  task_type: string;
  status: string;
  priority: string;
  phase_id: string | null;
  milestone_id: string | null;
  parent_id: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  start_date: string | null;
  due_date: string | null;
  estimate_min: number;
  spent_min: number;
  progress_pct: number;
  order_index: number;
  cis: Array<{ ci_id: string; code: string | null; name: string; role: string }>;
  time_entries: Array<{
    id: string;
    task_id: string;
    employee_id: string;
    employee_name: string | null;
    work_date: string;
    minutes: number;
    note: string;
  }>;
}

export interface ProjectDependency {
  id: string;
  predecessor_id: string;
  successor_id: string;
  dep_kind: string;
  lag_days: number;
}

export interface ScheduleItem {
  task_id: string;
  number: number;
  label: string;
  title: string;
  phase_id: string | null;
  parent_id: string | null;
  status: string;
  duration_days: number;
  es: number;
  ef: number;
  ls: number;
  lf: number;
  float_days: number;
  critical: boolean;
  start_date: string;
  finish_date: string;
  planned_start: string | null;
  planned_finish: string | null;
}

export interface ProjectView {
  project: {
    id: string;
    key: string;
    name: string;
    description: string;
    status: string;
    priority: string;
    owner_id: string | null;
    owner_name: string | null;
    start_date: string | null;
    due_date: string | null;
    actual_start_date: string | null;
    actual_end_date: string | null;
    budget_planned: number | null;
    budget_actual: number | null;
    progress_pct: number;
    task_count: number;
    open_task_count: number;
  };
  phases: ProjectPhase[];
  milestones: ProjectMilestone[];
  tasks: ProjectTask[];
  dependencies: ProjectDependency[];
  cis: Array<{
    ci_id: string;
    code: string | null;
    name: string;
    ci_type: string;
    involvement: string;
  }>;
  members: Array<{ employee_id: string; full_name: string; role: string }>;
  schedule: {
    anchor: string;
    length_days: number;
    items: ScheduleItem[];
    milestones: Array<{
      id: string;
      name: string;
      due_date: string | null;
      offset_days: number | null;
      status: string;
      overdue: boolean;
    }>;
  };
  health: {
    status: string;
    findings: Array<{ rule: string; level: string; message: string; entity_ids: string[] }>;
  };
}

export interface PowerWarning {
  code: string;
  message: string;
}

export interface PowerNodeRow {
  id: string;
  code: string | null;
  name: string;
  node_type: string;
  feed_id: string | null;
  feed_name: string | null;
  feed_side: string;
  nameplate_w: number;
  estimated_w: number;
  inlet_w: number;
  used_w: number;
  limit_w: number | null;
  headroom_w: number | null;
  current_a: number | null;
  disbalance_pct: number | null;
  phases_w: Record<string, number>;
  value_source: string;
  measured_coverage_pct: number;
  warnings: PowerWarning[];
  trace: Array<Record<string, unknown>>;
  failover: string | null;
  failover_detail: string | null;
  estimated_with_charge_w: number;
}

export interface PowerScenarioRow {
  id: string;
  name: string;
  description: string;
  project_id: string | null;
  project_key: string | null;
  charge_w: number;
  ups_efficiency: number | null;
  reserve: number;
  items: Array<{
    id: string;
    name: string;
    nameplate_w: number;
    quantity: number;
    utilization: number;
    behind_new_ups: boolean;
  }>;
  forecast: Record<string, number> | null;
}

export interface PowerOverview {
  nodes: PowerNodeRow[];
  feeds: Array<{ id: string; name: string; side: string; is_protected: boolean }>;
  links: Array<{
    id: string;
    source_node_id: string;
    target_node_id: string;
    source_name: string | null;
    target_name: string | null;
  }>;
  primary_input_id: string | null;
  scenarios: PowerScenarioRow[];
}

export interface TransitionGap {
  rule: string;
  level: string;
  message: string;
}

export interface TransitionView {
  live: {
    input_id: string | null;
    input_name: string | null;
    input_code: string | null;
    estimated_w: number | null;
    nameplate_w: number | null;
    limit_w: number | null;
    headroom_w: number | null;
    target_w: number | null;
    deficit_w: number | null;
    required_w: number | null;
    recommended_w: number | null;
    added_w: number | null;
  };
  snapshots: Array<{
    id: string;
    name: string;
    checksum: string;
    taken_at: string;
    estimated_w: number | null;
    limit_w: number | null;
    headroom_w: number | null;
    target_w: number | null;
    deficit_w: number | null;
  }>;
  plans: Array<{
    id: string;
    name: string;
    status: string;
    applied_at: string | null;
    gap: TransitionGap[];
    items: Array<{
      id: string;
      operation: string;
      entity_type: string;
      entity_id: string | null;
      payload: {
        ref?: string;
        summary?: string;
        fields?: { max_load_w?: number; rated_current_a?: number };
        before?: { max_load_w?: number; rated_current_a?: number | null };
      };
      apply_status: string;
      order_index: number;
    }>;
  }>;
  gap: TransitionGap[];
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

export interface VirtHost {
  id: string;
  name: string;
  code: string | null;
  ci_type: string;
  status: string;
  platform: string;
  cpu_cores: number;
  memory_mb: number;
  storage_gb: number;
  vm_count: number;
  vm_running: number;
  vcpu_running: number;
  memory_running_mb: number;
  vcpu_allocated: number;
  memory_allocated_mb: number;
  disk_allocated_gb: number;
}

export interface VirtVm {
  id: string;
  name: string;
  code: string | null;
  status: string;
  host_id: string | null;
  host_name: string | null;
  host_code: string | null;
  vcpu: number;
  memory_mb: number;
  disk_gb: number;
  guest_os: string | null;
  power_state: string;
}

export interface VirtOverview {
  hosts: VirtHost[];
  vms: VirtVm[];
  totals: {
    hosts: number;
    vms: number;
    running: number;
    vcpu_running: number;
    memory_running_mb: number;
    vcpu_allocated: number;
    memory_allocated_mb: number;
    disk_allocated_gb: number;
    cpu_cores: number;
    memory_mb: number;
    storage_gb: number;
  };
}
