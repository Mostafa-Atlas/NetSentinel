export type ApiError = {
  code: string;
  message: string;
  request_id?: string;
  details?: unknown;
};
export type Scope = {
  id: number;
  name: string;
  cidr: string;
  enabled: boolean;
  approved_at: string;
  max_concurrency: number;
  connect_timeout_ms: number;
  ports: number[];
};
export type Scan = {
  id: number;
  scope_id: number;
  type: string;
  status: "queued" | "running" | "completed" | "failed";
  started_at: string | null;
  finished_at: string | null;
  host_count: number;
  error_summary: string | null;
};
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type DeviceAddress = {
  ip: string;
  mac: string | null;
  hostname: string | null;
  first_seen_at: string;
  last_seen_at: string;
};
export type Device = {
  id: number;
  display_name: string;
  identity_confidence: "observed_mac" | "provisional";
  known_state: "known" | "unknown";
  notes: string;
  first_seen_at: string;
  last_seen_at: string;
  last_observed_at: string | null;
  status: "online" | "offline" | "unconfirmed";
  addresses: DeviceAddress[];
};
export type Observation = {
  id: number;
  scan_run_id: number;
  observed_at: string;
  source: string;
  reachable: boolean | null;
  latency_ms: number | null;
  raw_summary: string;
};
export type ServiceObservation = {
  id: number;
  scan_run_id: number;
  ip: string;
  port: number;
  protocol: string;
  state: "reachable" | "unreachable" | "unknown";
  observed_at: string;
};
export type MonitoringSettings = {
  schedule_enabled: boolean;
  interval_minutes: number;
  offline_threshold: number;
  retention_days: number;
};
export type Alert = {
  id: number;
  device_id: number | null;
  device_name: string | null;
  rule_key: string;
  severity: string;
  status: "active" | "acknowledged" | "resolved";
  summary: string;
  details: string;
  evidence_ref: string;
  created_at: string;
  last_seen_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
};
export type TimelineEvent = {
  id: number;
  device_id: number | null;
  event_type: string;
  occurred_at: string;
  actor: string;
  summary: string;
  evidence_ref: string | null;
};
export type Overview = {
  device_count: number;
  online_count: number;
  review_count: number;
  offline_count: number;
  active_alert_count: number;
  updated_at: string | null;
  latest_scan: Scan | null;
  recent_scans: Scan[];
  recent_events: Pick<
    TimelineEvent,
    "id" | "summary" | "event_type" | "occurred_at" | "actor"
  >[];
};
export type TopologyNode = {
  id: string;
  kind: "subnet" | "device";
  label: string;
  status: string;
  cidr?: string;
  device_id?: number;
  identity_confidence?: string;
  last_observed_at: string | null;
  addresses?: string[];
};
export type TopologyLink = {
  source: string;
  target: string;
  kind: "inferred";
  provenance: string;
};
export type Topology = {
  nodes: TopologyNode[];
  links: TopologyLink[];
  legend: { inferred: string };
};

function csrfToken(): string {
  const entry = document.cookie
    .split("; ")
    .find((part) => part.startsWith("netsentinel_csrf="));
  return entry
    ? decodeURIComponent(entry.slice("netsentinel_csrf=".length))
    : "";
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRF-Token": csrfToken() } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) throw data as ApiError;
  return data as T;
}
